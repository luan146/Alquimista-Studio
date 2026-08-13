from __future__ import annotations

from typing import Any

import pytest

from alquimista.errors import AlquimistaError
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


def test_legacy_runtime_builder_rejects_non_confluence_even_with_cached_tree() -> None:
    source = SourceConfig(
        id="gitbook", source_type="gitbook_api", selected_page_ids=["page-1"]
    )
    project = ProjectConfig(sources=[source])

    with pytest.raises(AlquimistaError, match="aceita apenas confluence_rest"):
        RuntimeBuilder(
            {"gitbook": {"root": {}, "pages": [{"id": "page-1"}]}},
            RuntimeSecrets(),
        ).build(project, CancellationToken(), lambda _message: None)


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

    assert listed == []
    assert runtimes[0].selected_page_ids == ["source:selected-space:page-1"]


def test_structured_selection_with_no_matching_container_never_scans_all() -> None:
    source = SourceConfig(id="source", source_type="confluence_rest")
    project = ProjectConfig(
        sources=[source],
        selections=[
            KnowledgeSelection(
                source_id="source",
                container_id="missing-space",
                document_id="page-1",
            )
        ],
    )
    listed: list[str] = []

    class Connector:
        def list_containers(self) -> list[KnowledgeContainer]:
            return [
                KnowledgeContainer(
                    id="available-space",
                    key="available-space",
                    name="Disponível",
                    container_type="space",
                    source_type="confluence_rest",
                )
            ]

        def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
            listed.append(container_id)
            return []

        def close(self) -> None:
            return None

    connector = Connector()

    class Registry:
        def create(self, _source: SourceConfig, **_kwargs: object) -> Connector:
            return connector

    runtimes = RuntimeBuilder({}, RuntimeSecrets(), Registry()).build_connectors(
        project, CancellationToken(), lambda _message: None
    )
    assert runtimes[0].selected_documents[0].metadata is not None

    assert listed == []


def test_lazy_root_snapshot_never_marks_inventory_complete() -> None:
    source = SourceConfig(id="source", source_type="confluence_rest")
    project = ProjectConfig(
        sources=[source],
        selections=[
            KnowledgeSelection(
                source_id="source",
                container_id="SPACE",
                document_id="root",
            )
        ],
    )

    class Connector:
        def list_containers(self) -> list[KnowledgeContainer]:
            return [
                KnowledgeContainer(
                    id="SPACE",
                    key="SPACE",
                    name="Espaço",
                    container_type="space",
                    source_type="confluence_rest",
                )
            ]

        def list_documents(self, _container_id: str) -> list[KnowledgeDocumentMetadata]:
            raise AssertionError("snapshot lazy não deve disparar inventário no builder")

        def close(self) -> None:
            return None

    connector = Connector()

    class Registry:
        def create(self, _source: SourceConfig, **_kwargs: object) -> Connector:
            return connector

    trees = {
        "source": {
            "pages_by_container": {
                "SPACE": [
                    {
                        "id": "root",
                        "title": "Raiz",
                        "_container_id": "SPACE",
                        "has_children": True,
                    }
                ]
            },
            "lazy_discovery": {
                "SPACE": {
                    "enabled": True,
                    "roots_complete": True,
                    "inventory_complete": False,
                    "full_loaded": False,
                }
            },
        }
    }

    runtime = RuntimeBuilder(trees, RuntimeSecrets(), Registry()).build_connectors(
        project, CancellationToken(), lambda _message: None
    )[0]

    assert runtime.inventory_complete_containers == set()
