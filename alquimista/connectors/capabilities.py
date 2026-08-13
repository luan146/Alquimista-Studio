"""Optional connector capabilities."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..browser.contracts import (
    CancellationLike,
    DiscoveryPage,
    DocumentMetadata,
    SearchResult,
)


@runtime_checkable
class HierarchicalDiscoveryConnector(Protocol):
    def list_root_documents(self, container_id: str, *, cursor: str | None = None,
                            limit: int = 100, etag: str | None = None,
                            token: CancellationLike | None = None) -> DiscoveryPage[DocumentMetadata]: ...
    def list_document_children(self, container_id: str, parent_id: str, *, cursor: str | None = None,
                               limit: int = 100, etag: str | None = None,
                               token: CancellationLike | None = None) -> DiscoveryPage[DocumentMetadata]: ...


@runtime_checkable
class SearchableConnector(Protocol):
    def search_documents(self, container_id: str | None, query: str, *, cursor: str | None = None,
                         limit: int = 100, etag: str | None = None,
                         token: CancellationLike | None = None) -> DiscoveryPage[SearchResult]: ...


@runtime_checkable
class MarkdownConfigurableConnector(Protocol):
    def configure_markdown(self, options: Any) -> None: ...
