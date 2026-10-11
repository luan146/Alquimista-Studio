from __future__ import annotations

from alquimista.models import (
    KnowledgeContainer,
    KnowledgeDocumentMetadata,
    KnowledgeSelection,
    ProjectConfig,
    SourceConfig,
)
from alquimista.runtime import CancellationToken
from alquimista.ui.controllers import RuntimeBuilder, RuntimeSecrets


def test_runtime_secrets_never_expose_a_serializable_mapping() -> None:
    secrets = RuntimeSecrets()
    secrets.set("source", "temporary-token")

    assert secrets.get("source") == "temporary-token"
    assert not hasattr(secrets, "to_dict")
    secrets.clear()
    assert secrets.get("source") == ""


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
