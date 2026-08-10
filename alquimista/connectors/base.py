from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..browser.contracts import (
    CancellationLike,
    DiscoveryPage,
    DocumentMetadata,
    SearchResult,
)
from ..models import (
    ConnectorCapabilities,
    KnowledgeContainer,
    KnowledgeDocument,
    KnowledgeDocumentMetadata,
    KnowledgeSource,
)


class KnowledgeSourceConnector(ABC):
    """Platform-neutral acquisition contract used by the ALQuimista core."""

    @abstractmethod
    def get_source_type(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_source(self) -> KnowledgeSource:
        raise NotImplementedError

    @abstractmethod
    def get_capabilities(self) -> ConnectorCapabilities:
        raise NotImplementedError

    @abstractmethod
    def validate_connection(self) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def list_containers(self) -> list[KnowledgeContainer]:
        raise NotImplementedError

    @abstractmethod
    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        raise NotImplementedError

    def list_root_documents(
        self,
        container_id: str,
        *,
        cursor: str | None = None,
        limit: int = 100,
        etag: str | None = None,
        token: CancellationLike | None = None,
    ) -> DiscoveryPage[DocumentMetadata]:
        """List only top-level documents when the provider supports it.

        This is deliberately concrete and optional: existing connectors keep
        working without implementing lazy discovery.  Callers must treat
        ``NotImplementedError`` as an explicit unsupported capability.
        """
        raise NotImplementedError(
            f"{type(self).__name__} não implementa descoberta lazy de raízes."
        )

    def list_document_children(
        self,
        container_id: str,
        parent_id: str,
        *,
        cursor: str | None = None,
        limit: int = 100,
        etag: str | None = None,
        token: CancellationLike | None = None,
    ) -> DiscoveryPage[DocumentMetadata]:
        """List direct children with the container kept in the request key."""
        raise NotImplementedError(
            f"{type(self).__name__} não implementa descoberta lazy de filhos."
        )

    def search_documents(
        self,
        container_id: str | None,
        query: str,
        *,
        cursor: str | None = None,
        limit: int = 100,
        etag: str | None = None,
        token: CancellationLike | None = None,
    ) -> DiscoveryPage[SearchResult]:
        """Search remote metadata, or fail explicitly when unavailable."""
        raise NotImplementedError(
            f"{type(self).__name__} não implementa busca remota de documentos."
        )

    @abstractmethod
    def get_document(
        self, document_id: str, container_id: str | None = None
    ) -> KnowledgeDocument:
        raise NotImplementedError

    @abstractmethod
    def get_document_children(
        self, document_id: str
    ) -> list[KnowledgeDocumentMetadata]:
        raise NotImplementedError

    @abstractmethod
    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        """Close connector-owned resources."""
        raise NotImplementedError

    def __enter__(self) -> "KnowledgeSourceConnector":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
