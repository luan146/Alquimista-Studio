"""Adapters from legacy source connectors to the lazy discovery contracts."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..connectors.base import KnowledgeSourceConnector
from ..connectors.capabilities import (
    HierarchicalDiscoveryConnector,
    SearchableConnector,
)
from ..models import KnowledgeContainer, KnowledgeDocumentMetadata
from .contracts import (
    CancellationLike,
    DiscoveryAdapter,
    DiscoveryPage,
    DocumentMetadata,
    SearchResult,
    SpaceMetadata,
    Visibility,
)


class DiscoveryCapabilityError(RuntimeError):
    """Raised instead of pretending a provider supports a lazy operation."""


class ConnectorDiscoveryAdapter(DiscoveryAdapter):
    """Expose an existing connector through the serializable discovery API."""

    def __init__(self, connector: KnowledgeSourceConnector) -> None:
        self.connector = connector

    @property
    def capabilities(self) -> frozenset[str]:
        capabilities = {"list_containers"}
        if isinstance(self.connector, HierarchicalDiscoveryConnector):
            capabilities.update({"list_root_documents", "list_document_children"})
        if isinstance(self.connector, SearchableConnector):
            capabilities.add("search_documents")
        return frozenset(capabilities)

    def list_containers(
        self,
        *,
        cursor: str | None,
        limit: int,
        etag: str | None,
        token: CancellationLike | None,
    ) -> DiscoveryPage[SpaceMetadata]:
        del etag
        _check_token(token)
        offset = _offset(cursor)
        containers = self.connector.list_containers()
        items = tuple(
            _space_metadata(self.connector.get_source().id, item)
            for item in containers[offset : offset + limit]
        )
        next_cursor = str(offset + limit) if offset + limit < len(containers) else None
        return DiscoveryPage(items=items, cursor=cursor, next_cursor=next_cursor)

    def list_root_documents(
        self,
        container_id: str,
        *,
        cursor: str | None,
        limit: int,
        etag: str | None,
        token: CancellationLike | None,
    ) -> DiscoveryPage[DocumentMetadata]:
        result = self._call_optional(
            "list_root_documents",
            container_id,
            cursor=cursor,
            limit=limit,
            etag=etag,
            token=token,
        )
        return _document_page(self.connector.get_source().id, result)

    def list_document_children(
        self,
        container_id: str,
        parent_id: str,
        *,
        cursor: str | None,
        limit: int,
        etag: str | None,
        token: CancellationLike | None,
    ) -> DiscoveryPage[DocumentMetadata]:
        result = self._call_optional(
            "list_document_children",
            container_id,
            parent_id,
            cursor=cursor,
            limit=limit,
            etag=etag,
            token=token,
        )
        return _document_page(self.connector.get_source().id, result)

    def search_documents(
        self,
        container_id: str | None,
        query: str,
        *,
        cursor: str | None,
        limit: int,
        etag: str | None,
        token: CancellationLike | None,
    ) -> DiscoveryPage[SearchResult]:
        result = self._call_optional(
            "search_documents",
            container_id,
            query,
            cursor=cursor,
            limit=limit,
            etag=etag,
            token=token,
        )
        if isinstance(result, DiscoveryPage):
            return DiscoveryPage(
                items=tuple(
                    item
                    if isinstance(item, SearchResult)
                    else SearchResult(document=_document_metadata(self.connector.get_source().id, item))
                    for item in result.items
                ),
                cursor=result.cursor,
                next_cursor=result.next_cursor,
                etag=result.etag,
            )
        raise TypeError("A busca lazy deve retornar DiscoveryPage[SearchResult].")

    def _call_optional(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if name not in self.capabilities:
            raise DiscoveryCapabilityError(
                f"O conector {type(self.connector).__name__} não expõe a capacidade {name}."
            )
        try:
            return getattr(self.connector, name)(*args, **kwargs)
        except NotImplementedError as exc:
            raise DiscoveryCapabilityError(str(exc)) from exc


def _offset(cursor: str | None) -> int:
    try:
        value = int(cursor or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError("cursor deve ser um offset inteiro") from exc
    if value < 0:
        raise ValueError("cursor não pode ser negativo")
    return value


def _space_metadata(source_id: str, value: KnowledgeContainer) -> SpaceMetadata:
    visibility = Visibility.parse(value.metadata.get("visibility"))
    return SpaceMetadata(
        source_id=source_id,
        id=str(value.id),
        name=value.name,
        container_type=value.container_type,
        description=value.description,
        parent_id=value.parent_id,
        updated_at=value.updated_at,
        visibility=visibility,
        metadata=_safe_metadata(value.metadata),
    )


def _document_page(source_id: str, value: Any) -> DiscoveryPage[DocumentMetadata]:
    if not isinstance(value, DiscoveryPage):
        raise TypeError("A descoberta lazy deve retornar DiscoveryPage[DocumentMetadata].")
    return DiscoveryPage(
        items=tuple(_document_metadata(source_id, item) for item in value.items),
        cursor=value.cursor,
        next_cursor=value.next_cursor,
        etag=value.etag,
        not_modified=value.not_modified,
    )


def _document_metadata(source_id: str, value: Any) -> DocumentMetadata:
    if isinstance(value, DocumentMetadata):
        return value
    if not isinstance(value, KnowledgeDocumentMetadata):
        raise TypeError("O conector retornou um tipo de documento não suportado.")
    raw_metadata = _safe_metadata(value.metadata)
    return DocumentMetadata(
        source_id=source_id,
        container_id=value.container_id,
        id=value.id,
        title=value.title,
        parent_id=value.parent_id,
        original_url=value.original_url,
        updated_at=value.updated_at,
        created_at=value.created_at,
        etag=value.etag,
        has_children=value.has_children,
        document_type=value.document_type,
        path=tuple(value.path),
        visibility=Visibility.parse(value.metadata.get("visibility")),
        metadata=raw_metadata,
    )


def _safe_metadata(value: object, *, depth: int = 0) -> dict[str, Any]:
    if depth > 4 or not isinstance(value, Mapping):
        return {}
    result: dict[str, Any] = {}
    blocked = ("body", "content", "html", "storage", "password", "secret", "token", "cookie", "credential")
    for key, item in value.items():
        name = str(key)
        if any(part in name.casefold() for part in blocked):
            continue
        if isinstance(item, Mapping):
            result[name] = _safe_metadata(item, depth=depth + 1)
        elif isinstance(item, (list, tuple)):
            result[name] = [str(entry) for entry in item[:100]]
        elif isinstance(item, (str, int, float, bool)) or item is None:
            result[name] = item
    return result


def _check_token(token: CancellationLike | None) -> None:
    if token is not None:
        token.check()
