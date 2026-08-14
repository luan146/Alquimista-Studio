from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from ..document_processing import get_global_processor_registry
from ..errors import ResourceNotFoundError
from ..models import (
    ConnectorCapabilities,
    ExtractionOptions,
    KnowledgeContainer,
    KnowledgeDocument,
    KnowledgeDocumentMetadata,
    KnowledgeSource,
    SourceConfig,
)
from ..runtime import CancellationToken, LogCallback
from .base import KnowledgeSourceConnector

IGNORED_PATTERNS = (
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "node_modules",
    ".DS_Store",
    "Thumbs.db",
)


def _should_ignore_file(file_path: Path) -> bool:
    name = file_path.name
    if name.startswith("~$") or name.startswith("."):
        return True
    for part in file_path.parts:
        if part in IGNORED_PATTERNS:
            return True
    return False


class LocalFilesConnector(KnowledgeSourceConnector):
    """Connector discovering, reading, and processing local files and folder trees."""

    SOURCE_TYPE = "local_files"

    def __init__(
        self,
        source: SourceConfig,
        options: ExtractionOptions,
        *,
        secret: str = "",
        token: CancellationToken | None = None,
        log: LogCallback | None = None,
        **_kwargs: Any,
    ) -> None:
        del secret
        self.source = source
        self.options = options
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        self.registry = get_global_processor_registry()
        raw_path = source.connector_options.get("path") or source.base_url
        self.root_path = Path(raw_path).resolve() if raw_path else Path.cwd()

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or self.root_path.name,
            base_url=str(self.root_path),
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_attachments=True,
            supports_public_access=True,
            supports_updated_at=True,
            supports_local_files=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        if not self.root_path.exists():
            raise ResourceNotFoundError(f"O caminho local não existe: {self.root_path}")
        return {
            "path": str(self.root_path),
            "is_dir": self.root_path.is_dir(),
            "exists": True,
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        if not self.root_path.exists():
            return []

        containers: list[KnowledgeContainer] = []
        if self.root_path.is_file():
            containers.append(
                KnowledgeContainer(
                    id="root",
                    key="root",
                    name=self.root_path.parent.name or "Arquivo",
                    container_type="folder",
                    source_type=self.SOURCE_TYPE,
                )
            )
            return containers

        # For directories, list folders containing supported files
        containers.append(
            KnowledgeContainer(
                id="root",
                key="root",
                name=self.root_path.name or "Raiz",
                container_type="folder",
                source_type=self.SOURCE_TYPE,
            )
        )

        supported_exts = self.registry.supported_extensions()
        for root, dirs, files in os.walk(self.root_path):
            self.token.check()
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in IGNORED_PATTERNS]
            rel_dir = Path(root).relative_to(self.root_path)
            if rel_dir == Path("."):
                continue

            has_supported_file = any(
                Path(f).suffix.lower() in supported_exts and not f.startswith("~$")
                for f in files
            )
            if has_supported_file:
                container_id = rel_dir.as_posix()
                containers.append(
                    KnowledgeContainer(
                        id=container_id,
                        key=container_id,
                        name=rel_dir.name or container_id,
                        container_type="folder",
                        source_type=self.SOURCE_TYPE,
                    )
                )

        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        if not self.root_path.exists():
            return []

        supported_exts = self.registry.supported_extensions()
        documents: list[KnowledgeDocumentMetadata] = []

        if self.root_path.is_file():
            if not _should_ignore_file(self.root_path):
                doc_id = hashlib.sha256(str(self.root_path).encode("utf-8")).hexdigest()
                documents.append(
                    KnowledgeDocumentMetadata(
                        id=doc_id,
                        container_id=container_id,
                        title=self.root_path.name,
                        original_url=str(self.root_path),
                    )
                )
            return documents

        target_dir = self.root_path if container_id == "root" else self.root_path / container_id
        if not target_dir.exists():
            return []

        try:
            for item in target_dir.iterdir():
                if item.is_file() and not _should_ignore_file(item):
                    if item.suffix.lower() in supported_exts:
                        doc_id = hashlib.sha256(item.resolve().as_posix().encode("utf-8")).hexdigest()
                        documents.append(
                            KnowledgeDocumentMetadata(
                                id=doc_id,
                                container_id=container_id,
                                title=item.name,
                                original_url=str(item.resolve()),
                                path=[container_id, item.name] if container_id != "root" else [item.name],
                            )
                        )
        except Exception as exc:
            self.log(f"Erro ao listar pasta {target_dir}: {exc}")

        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        self.token.check()
        # Find file matching document_id
        target_file: Path | None = None

        if self.root_path.is_file():
            target_file = self.root_path
        else:
            search_dir = self.root_path if (not container_id or container_id == "root") else self.root_path / container_id
            if search_dir.exists():
                for item in search_dir.iterdir():
                    if item.is_file() and not _should_ignore_file(item):
                        cand_id = hashlib.sha256(item.resolve().as_posix().encode("utf-8")).hexdigest()
                        if cand_id == document_id:
                            target_file = item
                            break

        if target_file is None or not target_file.exists():
            # Search whole tree as fallback
            for root, _dirs, files in os.walk(self.root_path):
                for f in files:
                    full = Path(root) / f
                    if not _should_ignore_file(full):
                        cand_id = hashlib.sha256(full.resolve().as_posix().encode("utf-8")).hexdigest()
                        if cand_id == document_id:
                            target_file = full
                            break
                if target_file:
                    break

        if target_file is None or not target_file.exists():
            raise ResourceNotFoundError(f"Arquivo local com ID {document_id} não foi encontrado.")

        metadata = {
            "source_id": self.source.id,
            "source_type": self.SOURCE_TYPE,
            "container_id": container_id or "root",
            "container_name": target_file.parent.name or "Pasta",
            "file_path": str(target_file.resolve()),
            "filename": target_file.name,
            "path": [container_id or "root", target_file.name],
        }

        doc = self.registry.process_file(target_file, metadata=metadata)
        # Ensure document attributes match connector expectations
        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or "root",
            parent_id=doc.parent_id,
            title=doc.title,
            content=doc.content,
            original_url=str(target_file.resolve()),
            created_at=doc.created_at,
            updated_at=doc.updated_at,
            etag=doc.etag,
            source_type=self.SOURCE_TYPE,
            container_name=target_file.parent.name or "Pasta",
            path=doc.path or [target_file.name],
            metadata=doc.metadata,
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if isinstance(raw_document, dict):
            return KnowledgeDocument.model_validate(raw_document)
        raise TypeError("Documento bruto deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        pass
