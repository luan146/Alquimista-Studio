from __future__ import annotations

from typing import Any

import pytest

from alquimista.models import (
    KnowledgeContainer,
    KnowledgeDocumentMetadata,
    KnowledgeSelection,
    ProjectConfig,
    SourceConfig,
    default_project,
)
from alquimista.runtime import CancellationToken
from alquimista.ui import controllers
from alquimista.ui.controllers import RuntimeBuilder, RuntimeSecrets


def test_runtime_secrets_never_expose_a_serializable_mapping() -> None:
    secrets = RuntimeSecrets()
    secrets.set("source", "temporary-token")

    assert secrets.get("source") == "temporary-token"
    assert not hasattr(secrets, "to_dict")
    secrets.clear()
    assert secrets.get("source") == ""


def test_runtime_builder_uses_cached_tree_without_network() -> None:
    project = default_project()
    source = SourceConfig(id="source", enabled=True, selected_page_ids=["10"])
    project.sources = [source]
    trees: dict[str, dict[str, Any]] = {
        "source": {
            "root": {"id": "10"},
            "pages": [{"id": "10", "title": "Root"}],
        }
    }

    runtimes = RuntimeBuilder(trees, RuntimeSecrets()).build(
        project, CancellationToken(), lambda _message: None
    )

    assert len(runtimes) == 1
    assert runtimes[0].pages_by_id["10"]["title"] == "Root"


def test_runtime_builder_fetches_missing_tree(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = default_project()
    source = SourceConfig(id="source", enabled=True, selected_page_ids=["20"])
    project.sources = [source]
    calls: list[str] = []

    class FakeClient:
        def __init__(self, source: SourceConfig, *_args: Any, **_kwargs: Any) -> None:
            calls.append(source.id)

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def fetch_tree(self) -> tuple[dict[str, str], list[dict[str, str]]]:
            return {"id": "20"}, [{"id": "20", "title": "Page"}]

    monkeypatch.setattr(controllers, "ConfluenceClient", FakeClient)

    runtimes = RuntimeBuilder({}, RuntimeSecrets()).build(
        project, CancellationToken(), lambda _message: None
    )

    assert calls == ["source"]
    assert runtimes[0].root["id"] == "20"


def test_runtime_builder_discovers_only_structured_selected_containers() -> None:
    source = SourceConfig(
        id="source",
        name="Confluence público",
        base_url="https://example.test",
        space_key="",
    )
    empty_source = SourceConfig(id="empty", name="Nova fonte", base_url="")
    project = ProjectConfig(
        output_dir="base",
        sources=[source, empty_source],
        selections=[
            KnowledgeSelection(
                source_id="source",
                container_id="selected-space",
                document_id="page-1",
            )
        ],
    )
    listed: list[str] = []

    class FakeConnector:
        def list_containers(self) -> list[KnowledgeContainer]:
            return [
                KnowledgeContainer(
                    id="selected-space",
                    key="selected-space",
                    name="Selecionado",
                    container_type="space",
                    source_type="confluence_rest",
                ),
                KnowledgeContainer(
                    id="unselected-space",
                    key="unselected-space",
                    name="Não selecionado",
                    container_type="space",
                    source_type="confluence_rest",
                ),
            ]

        def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
            listed.append(container_id)
            if container_id != "selected-space":
                raise AssertionError("espaço não selecionado não deveria ser consultado")
            return [
                KnowledgeDocumentMetadata(
                    id="page-1",
                    container_id=container_id,
                    title="Página selecionada",
                )
            ]

        def close(self) -> None:
            return None

    connector = FakeConnector()

    class Registry:
        def create(self, _source: SourceConfig, **_kwargs: object) -> FakeConnector:
            assert _source.id == "source"
            return connector

    runtimes = RuntimeBuilder({}, RuntimeSecrets(), Registry()).build_connectors(
        project,
        CancellationToken(),
        lambda _message: None,
    )

    assert listed == ["selected-space"]
    assert runtimes[0].selected_page_ids == ["source:selected-space:page-1"]
