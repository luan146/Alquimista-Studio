from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

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

    @abstractmethod
    def get_document(
        self, document_id: str, container_id: str | None = None
    ) -> KnowledgeDocument:
        raise NotImplementedError

    def get_document_children(
        self, document_id: str
    ) -> list[KnowledgeDocumentMetadata]:
        raise NotImplementedError

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
