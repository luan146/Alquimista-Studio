"""Serializable contracts for incremental knowledge-source discovery.

The contracts in this module describe discovery metadata only.  They do not
contain document bodies, credentials, cookies, or connector-specific clients.
Adapters for real providers can be injected into :class:`LazyDiscoveryService`
without coupling the discovery core to Qt or to an existing connector API.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Generic, Protocol, TypeVar

JsonScalar = str | int | float | bool | None
JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]


class Visibility(StrEnum):
    """Visibility reported by the provider, never inferred from login mode."""

    PUBLIC = "public"
    PRIVATE = "private"
    UNKNOWN = "unknown"

    @classmethod
    def parse(cls, value: object) -> "Visibility":
        if isinstance(value, cls):
            return value
        normalized = str(value or "").strip().casefold()
        aliases = {
            "public": cls.PUBLIC,
            "publico": cls.PUBLIC,
            "público": cls.PUBLIC,
            "private": cls.PRIVATE,
            "privado": cls.PRIVATE,
            "unknown": cls.UNKNOWN,
            "desconhecido": cls.UNKNOWN,
        }
        return aliases.get(normalized, cls.UNKNOWN)


def _datetime_to_json(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _datetime_from_json(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def _metadata_copy(value: Mapping[str, Any] | None) -> dict[str, Any]:
    return dict(value or {})


def _metadata_from_value(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


@dataclass(frozen=True, slots=True)
class SpaceMetadata:
    """Metadata for a source container (space, category, book, and so on)."""

    source_id: str
    id: str
    name: str
    container_type: str = "container"
    description: str | None = None
    parent_id: str | None = None
    updated_at: datetime | None = None
    etag: str | None = None
    visibility: Visibility = Visibility.UNKNOWN
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.id.strip():
            raise ValueError("source_id e id do contêiner são obrigatórios")
        object.__setattr__(self, "visibility", Visibility.parse(self.visibility))
        object.__setattr__(self, "metadata", _metadata_copy(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "id": self.id,
            "name": self.name,
            "container_type": self.container_type,
            "description": self.description,
            "parent_id": self.parent_id,
            "updated_at": _datetime_to_json(self.updated_at),
            "etag": self.etag,
            "visibility": self.visibility.value,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "SpaceMetadata":
        return cls(
            source_id=str(value["source_id"]),
            id=str(value["id"]),
            name=str(value.get("name") or value["id"]),
            container_type=str(value.get("container_type") or "container"),
            description=str(value["description"]) if value.get("description") is not None else None,
            parent_id=str(value["parent_id"]) if value.get("parent_id") is not None else None,
            updated_at=_datetime_from_json(value.get("updated_at")),
            etag=str(value["etag"]) if value.get("etag") is not None else None,
            visibility=Visibility.parse(value.get("visibility")),
            metadata=_metadata_from_value(value.get("metadata")),
        )


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    """Metadata for one document or tree node; it intentionally has no body."""

    source_id: str
    container_id: str
    id: str
    title: str
    parent_id: str | None = None
    original_url: str = ""
    updated_at: datetime | None = None
    created_at: datetime | None = None
    etag: str | None = None
    has_children: bool = False
    document_type: str = "document"
    path: tuple[str, ...] = ()
    visibility: Visibility = Visibility.UNKNOWN
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source_id.strip() or not self.container_id.strip() or not self.id.strip():
            raise ValueError("source_id, container_id e id do documento são obrigatórios")
        object.__setattr__(self, "visibility", Visibility.parse(self.visibility))
        object.__setattr__(self, "path", tuple(self.path))
        object.__setattr__(self, "metadata", _metadata_copy(self.metadata))

    @property
    def document_key(self) -> str:
        return f"{self.source_id}:{self.container_id}:{self.id}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "container_id": self.container_id,
            "id": self.id,
            "title": self.title,
            "parent_id": self.parent_id,
            "original_url": self.original_url,
            "updated_at": _datetime_to_json(self.updated_at),
            "created_at": _datetime_to_json(self.created_at),
            "etag": self.etag,
            "has_children": self.has_children,
            "document_type": self.document_type,
            "path": list(self.path),
            "visibility": self.visibility.value,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "DocumentMetadata":
        raw_path = value.get("path")
        return cls(
            source_id=str(value["source_id"]),
            container_id=str(value["container_id"]),
            id=str(value["id"]),
            title=str(value.get("title") or value["id"]),
            parent_id=str(value["parent_id"]) if value.get("parent_id") is not None else None,
            original_url=str(value.get("original_url") or ""),
            updated_at=_datetime_from_json(value.get("updated_at")),
            created_at=_datetime_from_json(value.get("created_at")),
            etag=str(value["etag"]) if value.get("etag") is not None else None,
            has_children=bool(value.get("has_children", False)),
            document_type=str(value.get("document_type") or "document"),
            path=tuple(str(item) for item in raw_path) if isinstance(raw_path, (list, tuple)) else (),
            visibility=Visibility.parse(value.get("visibility")),
            metadata=_metadata_from_value(value.get("metadata")),
        )


@dataclass(frozen=True, slots=True)
class PageRequest:
    """Opaque cursor request shared by all discovery operations."""

    cursor: str | None = None
    limit: int = 100

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("limit deve ser maior que zero")
        object.__setattr__(self, "cursor", self.cursor or None)


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class DiscoveryPage(Generic[T]):
    """One page of results and its opaque continuation cursor."""

    items: tuple[T, ...] = ()
    cursor: str | None = None
    next_cursor: str | None = None
    etag: str | None = None
    not_modified: bool = False
    from_cache: bool = False
    stale: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))
        object.__setattr__(self, "cursor", self.cursor or None)
        object.__setattr__(self, "next_cursor", self.next_cursor or None)

    @property
    def has_more(self) -> bool:
        return self.next_cursor is not None


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Search hit containing metadata only, never a body or content snippet."""

    document: DocumentMetadata
    match_kind: str = "title"
    score: float | None = None


class CancellationLike(Protocol):
    def check(self) -> None:
        """Raise when the caller has requested cancellation."""


class DiscoveryAdapter(Protocol):
    """Injectable provider adapter for lazy discovery.

    Implementations are expected to honor ``token`` between network pages and
    may use ``etag`` for conditional requests.  The current repository
    connectors are intentionally not modified by this module; a thin adapter
    can bridge them when their provider APIs support the operations.
    """

    def list_containers(
        self,
        *,
        cursor: str | None,
        limit: int,
        etag: str | None,
        token: CancellationLike | None,
    ) -> DiscoveryPage[SpaceMetadata]: ...

    def list_root_documents(
        self,
        container_id: str,
        *,
        cursor: str | None,
        limit: int,
        etag: str | None,
        token: CancellationLike | None,
    ) -> DiscoveryPage[DocumentMetadata]: ...

    def list_document_children(
        self,
        container_id: str,
        parent_id: str,
        *,
        cursor: str | None,
        limit: int,
        etag: str | None,
        token: CancellationLike | None,
    ) -> DiscoveryPage[DocumentMetadata]: ...

    def search_documents(
        self,
        container_id: str | None,
        query: str,
        *,
        cursor: str | None,
        limit: int,
        etag: str | None,
        token: CancellationLike | None,
    ) -> DiscoveryPage[SearchResult]: ...
