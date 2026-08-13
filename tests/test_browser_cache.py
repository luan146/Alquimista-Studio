from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from alquimista.browser import (
    BrowserCache,
    DiscoveryPage,
    DocumentMetadata,
    LazyDiscoveryService,
    SearchResult,
    SpaceMetadata,
    Visibility,
)


class FakeToken:
    def __init__(self) -> None:
        self.cancelled = False

    def check(self) -> None:
        if self.cancelled:
            raise RuntimeError("cancelled")


class FakeAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[object, ...]] = []

    def list_containers(self, *, cursor, limit, etag, token):
        self.calls.append(("containers", cursor, limit, etag))
        return DiscoveryPage(
            items=(SpaceMetadata("source", "space", "Space", visibility=Visibility.PUBLIC),),
            etag="spaces-v1",
        )

    def list_root_documents(self, container_id, *, cursor, limit, etag, token):
        self.calls.append(("root", container_id, cursor, limit, etag))
        return DiscoveryPage(
            items=(
                DocumentMetadata(
                    "source", container_id, "parent", "Parent", has_children=True, visibility=Visibility.UNKNOWN
                ),
            ),
            etag="root-v1",
        )

    def list_document_children(self, container_id, parent_id, *, cursor, limit, etag, token):
        self.calls.append(("children", container_id, parent_id, cursor, limit, etag))
        return DiscoveryPage(
            items=(DocumentMetadata("source", container_id, "child", "Child", parent_id=parent_id),),
            etag="children-v1",
        )

    def search_documents(self, container_id, query, *, cursor, limit, etag, token):
        self.calls.append(("search", container_id, query, cursor, limit, etag))
        document = DocumentMetadata("source", container_id or "space", "child", query)
        return DiscoveryPage(items=(SearchResult(document=document, match_kind="title"),), etag="search-v1")


def test_contracts_round_trip_and_visibility_does_not_infer_authentication() -> None:
    document = DocumentMetadata(
        "source",
        "space",
        "doc",
        "Página",
        parent_id="parent",
        path=("Parent", "Página"),
        visibility=Visibility.UNKNOWN,
    )

    restored = DocumentMetadata.from_dict(document.to_dict())

    assert restored == document
    assert restored.document_key == "source:space:doc"
    assert Visibility.parse("authenticated") is Visibility.UNKNOWN


def test_cache_is_idempotent_persistent_and_metadata_only(tmp_path: Path) -> None:
    path = tmp_path / "browser.sqlite3"
    space = SpaceMetadata(
        "source",
        "space",
        "Space",
        etag="v1",
        metadata={"owner": "team", "password": "must-not-persist", "description": "metadata"},
    )
    document = DocumentMetadata(
        "source",
        "space",
        "doc",
        "Doc",
        metadata={"body": "must-not-persist", "kind": "page"},
    )
    with BrowserCache(path) as cache:
        cache.put_containers("source", [space], ttl_seconds=60)
        cache.put_containers("source", [space], ttl_seconds=60)
        cache.put_documents("source", "space", [document], parent_id=None, ttl_seconds=60)

    with BrowserCache(path) as reopened:
        assert reopened.get_containers("source").items[0] == SpaceMetadata.from_dict(
            {**space.to_dict(), "metadata": {"owner": "team", "description": "metadata"}}
        )
        assert reopened.get_documents("source", "space").items[0].metadata == {"kind": "page"}

    connection = sqlite3.connect(path)
    try:
        payload = " ".join(str(row[0]) for row in connection.execute("SELECT payload FROM containers"))
        assert "must-not-persist" not in payload
        assert "password" not in payload
        assert "content" not in payload.casefold()
    finally:
        connection.close()


def test_cache_ttl_expires_pages_but_exposes_stale_etag(tmp_path: Path) -> None:
    now = [100.0]
    cache = BrowserCache(tmp_path / "browser.sqlite3", clock=lambda: now[0])
    cache.put_containers(
        "source",
        [SpaceMetadata("source", "space", "Space")],
        etag="spaces-v1",
        ttl_seconds=10,
    )

    assert cache.get_containers("source").etag == "spaces-v1"
    now[0] = 111.0
    assert cache.get_containers("source") is None
    stale = cache.get_containers("source", allow_stale=True)
    assert stale is not None
    assert stale.stale
    assert stale.etag == "spaces-v1"


def test_cache_purge_source_removes_all_scopes(tmp_path: Path) -> None:
    cache = BrowserCache(tmp_path / "browser.sqlite3")
    cache.put_containers("source", [SpaceMetadata("source", "space", "Privado")], scope="auth-a")
    cache.put_containers("source", [SpaceMetadata("source", "space", "Outra")], scope="auth-b")

    assert cache.purge_source("source") > 0
    assert cache.get_containers("source", scope="auth-a") is None
    assert cache.get_containers("source", scope="auth-b") is None


def test_service_is_cache_first_and_children_are_deduplicated(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    cache = BrowserCache(tmp_path / "browser.sqlite3")
    service = LazyDiscoveryService("source", adapter, cache=cache, cache_scope="public")

    first = service.list_containers()
    second = service.list_containers()
    root = service.list_root_documents("space")
    child_first = service.list_document_children("space", "parent")
    child_second = service.list_document_children("space", "parent")

    assert not first.from_cache
    assert second.from_cache
    assert root.items[0].has_children
    assert child_first.items == child_second.items
    assert [call[0] for call in adapter.calls] == ["containers", "root", "children"]
    assert service.cache_enabled

    cache.close()


def test_service_search_is_cached_without_persisting_query_text(tmp_path: Path) -> None:
    adapter = FakeAdapter()
    cache = BrowserCache(tmp_path / "browser.sqlite3")
    service = LazyDiscoveryService("source", adapter, cache=cache)

    first = service.search_documents("  página secreta  ", container_id="space")
    second = service.search_documents("página secreta", container_id="space")

    assert not first.from_cache
    assert second.from_cache
    assert len([call for call in adapter.calls if call[0] == "search"]) == 1
    connection = sqlite3.connect(cache.path)
    try:
        raw = json.dumps(list(connection.execute("SELECT * FROM search_pages")))
        assert "página secreta" not in raw
    finally:
        connection.close()


def test_service_without_cache_is_explicitly_network_only() -> None:
    adapter = FakeAdapter()
    service = LazyDiscoveryService("source", adapter)

    result = service.list_containers()

    assert not service.cache_enabled
    assert not result.from_cache
    assert len(adapter.calls) == 1


def test_service_checks_cancellation_before_adapter_call() -> None:
    adapter = FakeAdapter()
    token = FakeToken()
    token.cancelled = True
    service = LazyDiscoveryService("source", adapter)

    with pytest.raises(RuntimeError, match="cancelled"):
        service.list_containers(token=token)

    assert adapter.calls == []
