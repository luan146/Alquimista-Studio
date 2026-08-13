from __future__ import annotations

import json
from pathlib import Path

from golden_helpers import ROOT, assert_golden_text, read_json

from alquimista.connectors.confluence_parser import ConfluenceDocumentParser
from alquimista.models import MarkdownOptions, ProjectConfig, SourceConfig
from alquimista.services import ExtractionService, SourceRuntime


class _GoldenConnector:
    def __init__(self, document, secret: str) -> None:
        self.document = document
        self.secret = secret
        self.calls = 0

    def get_document(self, document_id: str, container_id: str | None = None):
        self.calls += 1
        assert document_id == self.document.id
        return self.document

    def close(self) -> None:
        return None


def test_confluence_extraction_manifest_and_hashes_are_stable(
    tmp_path: Path, monkeypatch
) -> None:
    page = json.loads(
        (ROOT / "confluence" / "page_full.json").read_text(encoding="utf-8")
    )
    secret = "GOLDEN_RUNTIME_SECRET_MUST_NOT_LEAK"
    source = SourceConfig(
        id="golden-source",
        name="Confluence golden",
        base_url="https://example.test",
        space_key="DOCS",
        space_name="Documentação",
        username="golden-user",
    )
    options = MarkdownOptions()
    document = ConfluenceDocumentParser(source, options).parse(page)
    project = ProjectConfig(
        project_id="golden-project",
        output_dir="base",
        sources=[source],
    )
    connector = _GoldenConnector(document, secret)
    runtime = SourceRuntime(
        source=source,
        root={},
        pages_by_id={},
        selected_page_ids=["golden-source:DOCS:page-42"],
        secret=secret,
        connector=connector,
        documents_by_container={
            "DOCS": {
                "page-42": type(
                    "Summary",
                    (),
                    {
                        "id": "page-42",
                        "title": document.title,
                        "updated_at": document.updated_at,
                        "etag": None,
                    },
                )()
            }
        },
    )
    monkeypatch.setattr("alquimista.services.now_iso", lambda: "2026-08-12T12:00:00-03:00")
    logs: list[str] = []
    first = ExtractionService(project, [runtime], tmp_path, log=logs.append).run()
    second = ExtractionService(project, [runtime], tmp_path, log=logs.append).run()
    assert first["counters"]["new"] == 1
    assert second["counters"]["unchanged"] == 1
    manifest = json.loads(
        (tmp_path / "base" / "manifesto_alquimista.json").read_text(encoding="utf-8")
    )
    entry = manifest["entries"][0]
    assert manifest["project_id"] == "golden-project"
    assert manifest["generated_at"] == "2026-08-12T12:00:00-03:00"
    assert entry["document_key"] == "golden-source:DOCS:page-42"
    expected_hashes = read_json(ROOT / "confluence" / "hashes.json")
    for field, expected in expected_hashes.items():
        assert entry[field] == expected
    output = (tmp_path / "base" / entry["markdown_path"]).read_text(
        encoding="utf-8"
    )
    assert_golden_text(
        output,
        ROOT / "confluence" / "approved_document_default.md",
        exact=True,
    )
    manifest_text = json.dumps(manifest, ensure_ascii=False, sort_keys=True)
    report_text = json.dumps([first, second], ensure_ascii=False, sort_keys=True)
    assert runtime.secret == secret
    assert connector.secret == secret
    assert secret not in output
    assert secret not in manifest_text
    assert secret not in report_text
    assert secret not in "\n".join(logs)
    for artifact in tmp_path.rglob("*"):
        if artifact.is_file():
            assert secret.encode("utf-8") not in artifact.read_bytes(), artifact
