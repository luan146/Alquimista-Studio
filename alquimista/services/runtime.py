from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..models import KnowledgeDocumentMetadata, SourceConfig


@dataclass(frozen=True, slots=True)
class SelectedDocumentRef:
    source_id: str
    container_id: str
    document_id: str
    metadata: KnowledgeDocumentMetadata | None = None
    summary_trusted: bool = False

    @property
    def document_key(self) -> str:
        return f"{self.source_id}:{self.container_id}:{self.document_id}"


@dataclass
class SourceRuntime:
    source: SourceConfig
    root: dict[str, Any]
    pages_by_id: dict[str, dict[str, Any]]
    # Historical field name retained for project compatibility. Values are
    # document keys for connector-backed runtimes.
    selected_page_ids: list[str]
    secret: str = ""
    connector: Any | None = None
    containers: dict[str, Any] | None = None
    documents_by_container: dict[str, dict[str, KnowledgeDocumentMetadata]] | None = None
    # Containers whose metadata snapshot represents a complete inventory.
    # Partial/lazy snapshots must not be interpreted as remote-removal scans.
    inventory_complete_containers: set[str] = field(default_factory=set)
    selected_documents: list[SelectedDocumentRef] = field(default_factory=list)

    @property
    def is_generic(self) -> bool:
        return self.connector is not None

    @property
    def selected_document_keys(self) -> list[str]:
        if self.selected_documents:
            return [item.document_key for item in self.selected_documents]
        if self.connector is None:
            return [f"{self.source.id}:{self.source.space_key}:{item}" for item in self.selected_page_ids]
        return list(self.selected_page_ids)


__all__ = ["SelectedDocumentRef", "SourceRuntime"]
