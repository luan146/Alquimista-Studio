from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from alquimista.connectors.registry import (
    ConnectorDescriptor,
    ConnectorFormSpec,
    ConnectorRegistry,
)
from alquimista.models import (
    AuthMode,
    ConnectorCapabilities,
    ConnectorStatus,
    KnowledgeContainer,
    KnowledgeDocumentMetadata,
    KnowledgeSelection,
    SourceConfig,
)
from alquimista.runtime import CancellationToken
from alquimista.source_detection import detect_source_url
from alquimista.ui.main_window import MainWindow


class _RoutingConnector:
    def __init__(self, source: SourceConfig, **_kwargs: Any) -> None:
        self.source = source
        self.closed = False
        self.list_documents_calls: list[str] = []

    def list_containers(self) -> list[KnowledgeContainer]:
        return [
            KnowledgeContainer(
                id="container-1",
                key="container-1",
                name="Container",
                container_type="space",
                source_type=self.source.source_type,
            )
        ]

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        self.list_documents_calls.append(container_id)
        return [
            KnowledgeDocumentMetadata(
                id="document-1",
                container_id=container_id,
                title="Documento",
            )
        ]

    def close(self) -> None:
        self.closed = True


def _descriptor(
    *,
    source_type: str = "fake_api",
    runnable: bool = True,
    lazy: bool = False,
    factory: Any = _RoutingConnector,
) -> ConnectorDescriptor:
    return ConnectorDescriptor(
        source_type=source_type,
        display_name="Fake",
        integration_name="Fake API",
        status=(ConnectorStatus.AVAILABLE if runnable else ConnectorStatus.DEVELOPMENT),
        implemented=runnable,
        capabilities=ConnectorCapabilities(supports_lazy_discovery=lazy),
        form=ConnectorFormSpec(bearer_only=True),
        factory=factory,
    )


def _run_worker_inline(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    def start(function: Any, done: Any) -> None:
        result = function(CancellationToken(), lambda *_args: None, lambda *_args: None)
        done(result)

    monkeypatch.setattr(window, "_start_worker", start)


def test_registered_runnable_connector_loads_containers_and_documents(
    qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = SourceConfig(id="fake-source", source_type="fake_api")
    created: list[_RoutingConnector] = []

    def factory(source: SourceConfig, **kwargs: Any) -> _RoutingConnector:
        connector = _RoutingConnector(source, **kwargs)
        created.append(connector)
        return connector

    descriptor = _descriptor(factory=factory)
    window.connector_registry = ConnectorRegistry([descriptor])
    _run_worker_inline(window, monkeypatch)

    window._load_tree_via_connector(source, descriptor=descriptor)
    window._load_container_for_source(
        source, "container-1", target="pages", load_all=True
    )

    assert window.trees[source.id]["containers"][0]["id"] == "container-1"
    assert window.trees[source.id]["pages_by_container"]["container-1"][0][
        "id"
    ] == "document-1"
    assert created[1].list_documents_calls == ["container-1"]
    assert all(connector.closed for connector in created)
    window.dirty = False


@pytest.mark.parametrize("source_type", ["development_api", "unknown_api"])
def test_non_runnable_or_unknown_never_calls_factory_or_confluence_fallback(
    qtbot, monkeypatch: pytest.MonkeyPatch, source_type: str
) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    calls: list[str] = []

    def factory(source: SourceConfig, **_kwargs: Any) -> _RoutingConnector:
        calls.append(source.source_type)
        return _RoutingConnector(source)

    descriptors = (
        [_descriptor(source_type=source_type, runnable=False, factory=factory)]
        if source_type == "development_api"
        else []
    )
    window.connector_registry = ConnectorRegistry(descriptors)
    source = SourceConfig(id="blocked-source", source_type=source_type)
    monkeypatch.setattr(window, "source_by_combo", lambda _combo: source)

    window.load_tree()

    assert calls == []
    assert window.worker is None
    assert "desenvolvimento" in window.tree_load_status.text().casefold() or (
        "não registrado" in window.tree_load_status.text().casefold()
    )
    window.dirty = False


def test_non_lazy_descriptor_uses_full_inventory_without_lazy_probe(
    qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = SourceConfig(id="fake-source", source_type="fake_api")
    descriptor = _descriptor(lazy=False)
    window.connector_registry = ConnectorRegistry([descriptor])
    window.trees[source.id] = {
        "containers": [{"id": "container-1", "name": "Container"}],
        "pages_by_container": {},
    }
    _run_worker_inline(window, monkeypatch)
    monkeypatch.setattr(
        window,
        "_lazy_discovery_page",
        lambda *_args, **_kwargs: pytest.fail("lazy não deveria ser consultado"),
    )

    window._load_container_for_source(source, "container-1", target="pages")

    assert window.trees[source.id]["lazy_discovery"]["container-1"]["enabled"] is False
    window.dirty = False


def test_platform_selection_is_draft_until_apply_and_invalidates_old_runtime_state(
    qtbot, monkeypatch: pytest.MonkeyPatch,
) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.current_source()
    assert source is not None
    original_type = source.source_type
    original_auth = source.auth_mode
    source.selected_page_ids = ["old-document"]
    source.consolidation_excluded_page_ids = ["old-document"]
    window.project.selections = [
        KnowledgeSelection(
            source_id=source.id,
            container_id="old-container",
            document_id="old-document",
        )
    ]
    window.selection_store.set(source.id, "old-container", "old-document", True)
    window.secrets.set(source.id, "old-secret")
    window.trees[source.id] = {"sentinel": "old-tree"}
    window.connected_sources.add(source.id)
    window.connection_states[source.id] = "old-connection"
    deleted: list[str] = []

    def delete_source_session(item: SourceConfig) -> bool:
        deleted.append(item.id)
        return True

    monkeypatch.setattr(
        "alquimista.ui.mixins.source_mixin.delete_session",
        delete_source_session,
    )
    development_index = window.src_platform.findData("notion_api")

    window.src_platform.setCurrentIndex(development_index)

    assert source.source_type == original_type
    assert source.auth_mode == original_auth
    assert window.secrets.get(source.id) == "old-secret"
    assert source.id in window.trees
    assert "Notion" in window.src_url_label.text()

    window.apply_source(silent=True)
    updated = window.current_source()
    assert updated is not None
    assert updated.source_type == "notion_api"
    assert updated.auth_mode is AuthMode.BEARER
    assert updated.selected_page_ids == []
    assert updated.consolidation_excluded_page_ids == []
    assert deleted == [source.id]
    assert window.secrets.get(source.id) == ""
    assert source.id not in window.trees
    assert source.id not in window.connected_sources
    assert source.id not in window.connection_states
    assert window.project.selections == []
    assert window.selection_store.keys_for_source(source.id) == set()
    window.dirty = False


def test_unknown_source_opens_blocked_without_converting_to_confluence(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = SourceConfig(
        id="future-source",
        name="Conector futuro",
        source_type="future_api",
        base_url="https://future.example.test",
    )
    window.project.sources = [source]

    window._refresh_source_widgets()

    assert window.current_source() is source
    assert window.src_platform.currentIndex() == -1
    assert window.src_platform.currentData() is None
    assert window.src_url.isEnabled() is False
    assert "não registrado" in window.src_autofill_status.text().casefold()
    assert "future_api" in window.source_table.item(0, 3).text()
    assert window.project.sources[0].source_type == "future_api"
    window.dirty = False


def test_final_root_page_is_not_a_complete_inventory(
    qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = SourceConfig(id="lazy-source", source_type="fake_api")
    descriptor = _descriptor(lazy=True)
    window.connector_registry = ConnectorRegistry([descriptor])
    window.trees[source.id] = {
        "containers": [{"id": "container-1", "name": "Container"}],
        "pages_by_container": {},
    }
    _run_worker_inline(window, monkeypatch)
    monkeypatch.setattr(
        window,
        "_lazy_discovery_page",
        lambda *_args, **_kwargs: SimpleNamespace(
            items=[
                KnowledgeDocumentMetadata(
                    id="root-1",
                    container_id="container-1",
                    title="Raiz",
                    has_children=True,
                )
            ],
            next_cursor=None,
            from_cache=False,
        ),
    )

    window._load_container_for_source(source, "container-1", target="pages")

    state = window.trees[source.id]["lazy_discovery"]["container-1"]
    assert state["roots_complete"] is True
    assert state["inventory_complete"] is False
    assert state["full_loaded"] is False
    assert window._container_requires_full_load(
        window.trees[source.id], "container-1"
    ) is True
    window.dirty = False


def test_non_confluence_autofill_preserves_connector_api_url(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    window.src_platform.setCurrentIndex(window.src_platform.findData("gitbook_api"))
    window.src_url.setText("https://docs.gitbook.io/manual")

    window._autofill_source_url()

    assert window.src_url.text() == "https://api.gitbook.com/v1"
    assert window.src_space.text() == "manual"
    window.dirty = False


def test_status_and_sharepoint_detection_are_boundary_safe() -> None:
    descriptor = ConnectorDescriptor(
        source_type="blocked",
        display_name="Blocked",
        integration_name="Blocked",
        status="Indisponível",
        implemented=True,
        capabilities=ConnectorCapabilities(),
        factory=_RoutingConnector,
    )
    assert descriptor.status_code is ConnectorStatus.UNAVAILABLE
    assert detect_source_url("https://evilsharepoint.com/manual").source_type == "generic_web"
