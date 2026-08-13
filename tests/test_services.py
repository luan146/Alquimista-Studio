from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pytest

import alquimista.services as services
from alquimista.errors import ExtractionCancelledError, ManifestError
from alquimista.models import (
    EntryStatus,
    ManifestDocument,
    ManifestEntry,
    ProjectConfig,
    SourceConfig,
)
from alquimista.runtime import CancellationToken
from alquimista.services import ConsolidationService, ExtractionService, SourceRuntime
from alquimista.storage import FileTransaction, ManifestStore


def page(
    page_id: str,
    title: str,
    body: str,
    *,
    version: int = 1,
    source_space: str = "DOC",
) -> dict[str, Any]:
    return {
        "id": page_id,
        "type": "page",
        "title": title,
        "ancestors": [
            {"id": "100", "title": "Manual"},
            {"id": "110", "title": "Módulo"},
        ],
        "space": {"key": source_space, "name": f"Espaço {source_space}"},
        "version": {
            "number": version,
            "when": f"2026-07-{version:02d}T10:00:00Z",
            "by": {"displayName": "Analista"},
        },
        "metadata": {"labels": {"results": [{"name": "manual"}]}},
        "body": {"storage": {"value": body}},
        "_links": {"webui": f"/pages/viewpage.action?pageId={page_id}"},
    }


class FakeClient:
    pages: dict[tuple[str, str], dict[str, Any]] = {}
    body_fetches = 0

    def __init__(self, source, options, **kwargs):
        self.source = source
        self.base_url = source.base_url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def fetch_page(self, page_id, *, include_body, include_labels=False):
        if include_body:
            FakeClient.body_fetches += 1
        result = dict(FakeClient.pages[(self.source.id, str(page_id))])
        if not include_body:
            result.pop("body", None)
        return result

    @staticmethod
    def source_url(base_url, page):
        return f"{base_url}/pages/viewpage.action?pageId={page['id']}"


@pytest.fixture
def configured(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(services, "ConfluenceClient", FakeClient)
    source = SourceConfig(
        id="fonte1",
        name="Produto",
        base_url="https://example.test",
        space_key="DOC",
        root_mode="id",
        root_value="100",
    )
    project = ProjectConfig(project_name="Teste", output_dir="base", sources=[source])
    root = {
        "id": "100",
        "title": "Manual",
        "space": {"key": "DOC", "name": "Documentação"},
    }
    current = page("10", "Venda", "<p>Conteúdo</p>")
    FakeClient.pages = {(source.id, "10"): current}
    FakeClient.body_fetches = 0
    summary = dict(current)
    summary.pop("body")
    runtime = SourceRuntime(source, root, {"10": summary}, ["10"])
    return project, runtime, current, tmp_path


def test_incremental_statuses_and_no_unnecessary_body_fetch(configured):
    project, runtime, current, base = configured
    first = ExtractionService(project, [runtime], base).run()
    assert first["counters"]["new"] == 1
    assert FakeClient.body_fetches == 1
    second = ExtractionService(project, [runtime], base).run()
    assert second["counters"]["unchanged"] == 1
    assert FakeClient.body_fetches == 1
    changed = page("10", "Venda", "<p>Conteúdo alterado</p>", version=2)
    FakeClient.pages[("fonte1", "10")] = changed
    summary = dict(changed)
    summary.pop("body")
    runtime.pages_by_id["10"] = summary
    third = ExtractionService(project, [runtime], base).run()
    assert third["counters"]["updated"] == 1


def test_markdown_filename_uses_page_title(configured):
    project, runtime, _current, base = configured
    result = ExtractionService(project, [runtime], base).run()
    manifest = json.loads(
        (base / "base" / "manifesto_alquimista.json").read_text(encoding="utf-8")
    )
    assert manifest["entries"][0]["title"] == "Venda"
    assert manifest["entries"][0]["markdown_path"].endswith("/Venda.md")
    assert result["counters"]["new"] == 1


def test_default_markdown_is_compact_and_shared_by_loose_files(configured):
    project, runtime, _current, base = configured
    ExtractionService(project, [runtime], base).run()
    manifest = json.loads(
        (base / "base" / "manifesto_alquimista.json").read_text(encoding="utf-8")
    )
    markdown_path = base / "base" / manifest["entries"][0]["markdown_path"]
    text = markdown_path.read_text(encoding="utf-8")
    assert text.startswith("# Venda\n\n")
    assert "**Fonte original:**" not in text
    assert "**URL original:** [Abrir no Confluence]" in text
    assert "**Módulo:**" in text
    assert "**Caminho:**" in text
    assert "**Última atualização:**" in text
    assert "**SHA-256:** `" in text
    assert "ALQUIMISTA_DOCUMENT_START" not in text
    assert "## Conteúdo técnico" in text


def test_same_page_id_in_two_sources_does_not_collide(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(services, "ConfluenceClient", FakeClient)
    sources = [
        SourceConfig(id="s1", name="A", base_url="https://a.test", space_key="A"),
        SourceConfig(id="s2", name="B", base_url="https://b.test", space_key="B"),
    ]
    project = ProjectConfig(output_dir="base", sources=sources)
    runtimes = []
    for source in sources:
        root = {"id": "100", "title": "Manual", "space": {"key": source.space_key}}
        full = page("10", source.name, f"<p>{source.name}</p>", source_space=source.space_key)
        FakeClient.pages[(source.id, "10")] = full
        summary = dict(full)
        summary.pop("body")
        runtimes.append(SourceRuntime(source, root, {"10": summary}, ["10"]))
    ExtractionService(project, runtimes, tmp_path).run()
    manifest = json.loads(
        (tmp_path / "base" / "manifesto_alquimista.json").read_text(encoding="utf-8")
    )
    assert {entry["document_key"] for entry in manifest["entries"]} == {"s1:10", "s2:10"}
    assert len({entry["markdown_path"] for entry in manifest["entries"]}) == 2


def test_consolidation_splits_without_splitting_a_page(configured):
    project, runtime, _current, base = configured
    ExtractionService(project, [runtime], base).run()
    project.consolidation.max_pages = 1
    preview = ConsolidationService(project, base).preview()
    assert preview[0]["pages"] == 1
    result = ConsolidationService(project, base).run()
    assert result["packages"] == 1
    package = next((base / "base" / project.consolidation.output_subdir).glob("*.md"))
    package_text = package.read_text(encoding="utf-8")
    assert "Abrir no Confluence" in package_text
    assert "## Índice" in package_text
    assert "[Venda]" in package_text
    assert "# Venda" in package_text
    assert "## Venda" not in package_text


def test_consolidation_can_render_explicit_hierarchy_headings(configured):
    project, runtime, _current, base = configured
    ExtractionService(project, [runtime], base).run()
    project.consolidation.include_hierarchy_headings = True
    ConsolidationService(project, base).run()
    package = next((base / "base" / project.consolidation.output_subdir).glob("*.md"))
    package_text = package.read_text(encoding="utf-8")
    assert "## Manual" in package_text


def test_consolidation_cancels_during_long_preview_read(configured, monkeypatch):
    project, runtime, _current, base = configured
    ExtractionService(project, [runtime], base).run()
    token = CancellationToken()
    service = ConsolidationService(project, base, token=token)
    original_page_text = service._page_text

    def cancel_during_read(entry):
        text = original_page_text(entry)
        token.cancel()
        return text

    monkeypatch.setattr(service, "_page_text", cancel_during_read)

    with pytest.raises(ExtractionCancelledError):
        service.preview()


def test_consolidation_cancels_before_next_package(configured):
    project, runtime, _current, base = configured
    ExtractionService(project, [runtime], base).run()
    second = page("11", "Suporte", "<p>Conteúdo de suporte</p>")
    FakeClient.pages[(runtime.source.id, "11")] = second
    second_summary = dict(second)
    second_summary.pop("body")
    runtime.pages_by_id["11"] = second_summary
    runtime.selected_page_ids.append("11")
    ExtractionService(project, [runtime], base).run()
    project.consolidation.max_pages = 1
    token = CancellationToken()
    service = ConsolidationService(project, base, token=token)

    def cancel_after_first_package(done, _total, _filename):
        if done == 1:
            token.cancel()

    service.progress = cancel_after_first_package

    with pytest.raises(ExtractionCancelledError):
        service.run()


def test_module_consolidation_depth_uses_hierarchy(tmp_path: Path):
    source = SourceConfig(id="s1", name="Produto", space_key="DOC")
    project = ProjectConfig(output_dir="base", sources=[source])
    project.consolidation.grouping = "module"
    project.consolidation.module_depth = 1
    service = ConsolidationService(project, tmp_path)
    entry = ManifestEntry(
        source_id="s1",
        source_name="Produto",
        space_key="DOC",
        page_id="10",
        document_key="s1:10",
        title="Página",
        path=["Base", "Operação", "Configuração", "Página"],
    )
    assert service._group_key(entry) == "Operação"
    project.consolidation.module_depth = 2
    assert service._group_key(entry) == "Operação__Configuração"


def test_module_consolidation_depth_generates_expected_packages_and_index(tmp_path: Path):
    """Validate the end-to-end level-1/level-2 grouping used by the UI."""
    source = SourceConfig(id="s1", name="Produto", space_key="DOC")
    project = ProjectConfig(project_name="Profundidade", output_dir="base", sources=[source])
    base = tmp_path / "base"
    base.mkdir()
    entries: list[ManifestEntry] = []
    pages = [
        ("10", "Visão geral", ["Base", "Operação", "Visão geral"]),
        ("11", "Login", ["Base", "Operação", "Login"]),
        (
            "12",
            "Detalhes",
            ["Base", "Operação", "Configuração", "Detalhes"],
        ),
    ]
    for page_id, title, path in pages:
        relative = Path("paginas") / f"{page_id}.md"
        (base / relative).parent.mkdir(parents=True, exist_ok=True)
        (base / relative).write_text(f"# {title}\n\nConteudo de {title}.", encoding="utf-8")
        entries.append(
            ManifestEntry(
                source_id="s1",
                page_id=page_id,
                document_key=f"s1:{page_id}",
                title=title,
                source_url=f"https://example.test/pages/viewpage.action?pageId={page_id}",
                source_name="Produto",
                space_key="DOC",
                root_page_id="100",
                root_title="Manual",
                module=path[1],
                path=path,
                markdown_path=relative.as_posix(),
            )
        )
    ManifestStore(base / "manifesto_alquimista.json", project).save(
        ManifestDocument(project_id=project.project_id, project_name=project.project_name, entries=entries)
    )

    project.consolidation.grouping = "module"
    project.consolidation.module_depth = 1
    level_one = ConsolidationService(project, tmp_path)
    assert len(level_one.preview()) == 1
    result_one = level_one.run()
    assert result_one["packages"] == 1
    index_one = json.loads(
        (base / project.consolidation.output_subdir / "indice_pacotes_alquimista.json").read_text(encoding="utf-8")
    )
    assert index_one["packages"][0]["pages"] == 3

    project.consolidation.module_depth = 2
    level_two = ConsolidationService(project, tmp_path)
    assert {item["group"] for item in level_two.preview()} == {
        "Operação",
        "Operação__Configuração",
    }
    result_two = level_two.run()
    assert result_two["packages"] == 2
    output = base / project.consolidation.output_subdir
    package_text = "\n".join(path.read_text(encoding="utf-8") for path in output.glob("*.md"))
    assert "[Visão geral]" in package_text
    assert "[Detalhes]" in package_text


def test_partial_update_preserves_entries_outside_retry_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(services, "ConfluenceClient", FakeClient)
    source = SourceConfig(
        id="s1",
        name="Produto",
        base_url="https://example.test",
        root_mode="id",
        root_value="100",
    )
    project = ProjectConfig(output_dir="base", sources=[source])
    root = {"id": "100", "title": "Manual", "space": {"key": "DOC"}}
    full_pages = {
        "10": page("10", "Dez", "<p>10</p>"),
        "11": page("11", "Onze", "<p>11</p>"),
    }
    FakeClient.pages = {("s1", key): value for key, value in full_pages.items()}
    summaries = {key: dict(value) for key, value in full_pages.items()}
    for summary in summaries.values():
        summary.pop("body")
    ExtractionService(
        project,
        [SourceRuntime(source, root, summaries, ["10", "11"])],
        tmp_path,
    ).run()

    ExtractionService(
        project,
        [SourceRuntime(source, root, summaries, ["10"])],
        tmp_path,
        partial_update_keys={"s1:10"},
    ).run()

    manifest = ManifestStore(tmp_path / "base" / "manifesto_alquimista.json", project).load()
    healthy = next(entry for entry in manifest.entries if entry.page_id == "11")
    assert healthy.active
    assert healthy.selected
    assert healthy.status.value == "new"


def test_reconciliation_preserves_missing_descendant_until_inventory_is_complete(
    tmp_path: Path,
) -> None:
    source = SourceConfig(id="source", space_key="SPACE")
    project = ProjectConfig(output_dir="base", sources=[source])
    project.extraction.detect_remote_removals = True
    service = ExtractionService(project, [], tmp_path)
    root_key = "source:SPACE:root"
    child_key = "source:SPACE:child"
    previous = {
        root_key: ManifestEntry(
            source_id="source",
            container_id="SPACE",
            document_id="root",
            page_id="root",
            document_key=root_key,
            title="Raiz",
        ),
        child_key: ManifestEntry(
            source_id="source",
            container_id="SPACE",
            document_id="child",
            page_id="child",
            document_key=child_key,
            title="Descendente",
        ),
    }

    lazy_current: dict[str, ManifestEntry] = {}
    with FileTransaction(tmp_path / "base") as transaction:
        service._reconcile_manifest(
            previous=previous,
            current=lazy_current,
            discovered_keys={root_key},
            selected_keys={root_key},
            complete_containers=set(),
            counters=Counter(),
            transaction=transaction,
            collected_at="2026-08-13T12:00:00-03:00",
        )
    assert lazy_current[child_key].status is EntryStatus.NEW
    assert lazy_current[child_key].active is True

    complete_current: dict[str, ManifestEntry] = {}
    with FileTransaction(tmp_path / "base") as transaction:
        service._reconcile_manifest(
            previous=previous,
            current=complete_current,
            discovered_keys={root_key},
            selected_keys={root_key},
            complete_containers={("source", "SPACE")},
            counters=Counter(),
            transaction=transaction,
            collected_at="2026-08-13T12:01:00-03:00",
        )
    assert complete_current[child_key].status is EntryStatus.REMOVED
    assert complete_current[child_key].active is False


def test_empty_page_has_explicit_status_instead_of_removed(configured) -> None:
    project, runtime, _current, base = configured
    ExtractionService(project, [runtime], base).run()
    empty = page("10", "Venda", "", version=2)
    FakeClient.pages[("fonte1", "10")] = empty
    summary = dict(empty)
    summary.pop("body")
    runtime.pages_by_id["10"] = summary

    ExtractionService(project, [runtime], base).run()

    entry = ManifestStore(base / "base" / "manifesto_alquimista.json", project).load().entries[0]
    assert entry.status.value == "empty_skipped"
    assert not entry.active
    assert entry.selected
    with pytest.raises(Exception):
        ConsolidationService(project, base).preview()


@pytest.mark.parametrize("content", [None, ""])
def test_consolidation_rejects_missing_or_empty_manifest_file(
    tmp_path: Path, content: str | None
) -> None:
    source = SourceConfig(id="s1")
    project = ProjectConfig(output_dir="base", sources=[source])
    base = tmp_path / "base"
    base.mkdir()
    relative = Path("pages") / "missing.md"
    if content is not None:
        (base / relative).parent.mkdir()
        (base / relative).write_text(content, encoding="utf-8")
    entry = ManifestEntry(
        source_id="s1",
        page_id="1",
        document_key="s1:1",
        title="Ausente",
        path=["Manual", "Ausente"],
        markdown_path=relative.as_posix(),
    )
    ManifestStore(base / "manifesto_alquimista.json", project).save(
        ManifestDocument(
            project_id=project.project_id,
            project_name=project.project_name,
            entries=[entry],
        )
    )

    with pytest.raises(ManifestError, match="manifesto_alquimista.json"):
        ConsolidationService(project, tmp_path).run()

    assert not (base / project.consolidation.output_subdir).exists()


def test_colliding_group_names_generate_distinct_packages(tmp_path: Path) -> None:
    source = SourceConfig(id="s1")
    project = ProjectConfig(output_dir="base", sources=[source])
    project.consolidation.grouping = "manual"
    base = tmp_path / "base"
    (base / "pages").mkdir(parents=True)
    entries: list[ManifestEntry] = []
    for page_id, title, group in [
        ("1", "Primeira", "A/B"),
        ("2", "Segunda", "AB"),
    ]:
        relative = Path("pages") / f"{page_id}.md"
        (base / relative).write_text(f"# {title}\n", encoding="utf-8")
        key = f"s1:{page_id}"
        project.consolidation.manual_groups[key] = group
        entries.append(
            ManifestEntry(
                source_id="s1",
                page_id=page_id,
                document_key=key,
                title=title,
                path=["Manual", title],
                markdown_path=relative.as_posix(),
            )
        )
    ManifestStore(base / "manifesto_alquimista.json", project).save(
        ManifestDocument(
            project_id=project.project_id,
            project_name=project.project_name,
            entries=entries,
        )
    )

    result = ConsolidationService(project, tmp_path).run()
    output = base / project.consolidation.output_subdir
    package_files = sorted(path.name for path in output.glob("*.md"))
    index = json.loads(
        (output / "indice_pacotes_alquimista.json").read_text(encoding="utf-8")
    )

    assert result["packages"] == 2
    assert len(package_files) == 2
    assert len({item["filename"].casefold() for item in index["packages"]}) == 2
