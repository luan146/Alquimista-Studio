from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from alquimista.browser import DiscoveryPage, DocumentMetadata
from alquimista.models import AuthMode, KnowledgeSource, default_project
from alquimista.runtime import CancellationToken
from alquimista.ui import main_window as main_window_module
from alquimista.ui.main_window import MainWindow


class _DiscoveryConnectorDouble:
    def __init__(self, source_id: str) -> None:
        self.source = KnowledgeSource(
            id=source_id,
            source_type="confluence_rest",
            name="Fonte de teste",
            base_url="https://example.test",
        )
        self.root_calls = 0
        self.children_calls: list[tuple[str, str]] = []

    def get_source(self) -> KnowledgeSource:
        return self.source

    def list_root_documents(self, container_id: str, **_kwargs: object) -> DiscoveryPage[DocumentMetadata]:
        self.root_calls += 1
        return DiscoveryPage(
            items=(
                DocumentMetadata(
                    self.source.id,
                    container_id,
                    "parent",
                    "Página pública",
                    has_children=True,
                    metadata={"body": "não persistir", "token": "segredo-teste", "kind": "page"},
                ),
            ),
            etag="root-v1",
        )

    def list_document_children(
        self,
        container_id: str,
        parent_id: str,
        **_kwargs: object,
    ) -> DiscoveryPage[DocumentMetadata]:
        self.children_calls.append((container_id, parent_id))
        return DiscoveryPage(
            items=(
                DocumentMetadata(
                    self.source.id,
                    container_id,
                    "child",
                    "Filho",
                    parent_id=parent_id,
                    metadata={"body": "não persistir", "token": "segredo-teste"},
                ),
            ),
            etag="children-v1",
        )


def test_ui_lazy_discovery_reuses_metadata_cache_without_secret_or_body(
    tmp_path: Path, monkeypatch
) -> None:
    session_dir = tmp_path / "sessions"
    monkeypatch.setattr(main_window_module, "session_directory", lambda: session_dir)
    source = default_project().sources[0].model_copy(update={"auth_mode": AuthMode.BEARER})
    token = CancellationToken()

    first_connector = _DiscoveryConnectorDouble(source.id)
    first_root = MainWindow._lazy_discovery_page(
        source,
        first_connector,
        "space-a",
        parent_id=None,
        token=token,
    )
    first_children = MainWindow._lazy_discovery_page(
        source,
        first_connector,
        "space-a",
        parent_id="parent",
        token=token,
    )

    second_connector = _DiscoveryConnectorDouble(source.id)
    cached_root = MainWindow._lazy_discovery_page(
        source,
        second_connector,
        "space-a",
        parent_id=None,
        token=token,
    )
    cached_children = MainWindow._lazy_discovery_page(
        source,
        second_connector,
        "space-a",
        parent_id="parent",
        token=token,
    )

    assert first_root is not None and not first_root.from_cache
    assert first_children is not None and not first_children.from_cache
    assert cached_root is not None and cached_root.from_cache
    assert cached_children is not None and cached_children.from_cache
    assert first_connector.root_calls == 1
    assert first_connector.children_calls == [("space-a", "parent")]
    assert second_connector.root_calls == 0
    assert second_connector.children_calls == []

    cache_path = session_dir.parent / "browser_metadata.sqlite3"
    assert cache_path.exists()
    connection = sqlite3.connect(cache_path)
    try:
        raw = json.dumps(list(connection.execute("SELECT payload FROM documents")))
    finally:
        connection.close()
    assert "segredo-teste" not in raw
    assert "não persistir" not in raw
    assert "body" not in raw.casefold()
    assert "token" not in raw.casefold()
