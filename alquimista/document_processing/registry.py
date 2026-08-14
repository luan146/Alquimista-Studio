from __future__ import annotations

from pathlib import Path
from typing import Any

from ..errors import StorageError
from ..models import KnowledgeDocument
from .base import DocumentProcessor
from .ebook import EbookProcessor
from .html import HtmlProcessor
from .image import ImageProcessor
from .pdf import PdfProcessor
from .presentation import PresentationProcessor
from .spreadsheet import SpreadsheetProcessor
from .text import TextProcessor
from .word import WordProcessor

MAX_DOCUMENT_SIZE_BYTES = 100 * 1024 * 1024  # 100 MiB


class DocumentProcessorRegistry:
    """Registry coordinating document processors across all supported formats."""

    def __init__(self, processors: list[DocumentProcessor] | None = None) -> None:
        self._processors: list[DocumentProcessor] = list(processors or [])

    def register(self, processor: DocumentProcessor) -> None:
        self._processors.insert(0, processor)

    def get_processor(
        self,
        file_path: Path | str | None = None,
        mime_type: str | None = None,
        file_bytes: bytes | None = None,
    ) -> DocumentProcessor | None:
        for processor in self._processors:
            if processor.can_process(file_path=file_path, mime_type=mime_type, file_bytes=file_bytes):
                return processor
        return None

    def supported_extensions(self) -> set[str]:
        exts: set[str] = set()
        for p in self._processors:
            exts.update(p.supported_extensions)
        return exts

    def supported_mimetypes(self) -> set[str]:
        mimes: set[str] = set()
        for p in self._processors:
            mimes.update(p.supported_mimetypes)
        return mimes

    def process_file(
        self,
        file_path: Path | str,
        *,
        metadata: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> KnowledgeDocument:
        path = Path(file_path)
        if not path.exists():
            raise StorageError(f"Arquivo não encontrado: {path}")
        if path.is_file() and path.stat().st_size > MAX_DOCUMENT_SIZE_BYTES:
            raise StorageError(
                f"Arquivo {path.name} excede o limite máximo permitido de "
                f"{MAX_DOCUMENT_SIZE_BYTES // (1024 * 1024)} MiB."
            )

        processor = self.get_processor(file_path=path)
        if processor is None:
            # Fallback to TextProcessor if nothing matched
            processor = TextProcessor()

        return processor.process_file(path, metadata=metadata, options=options)

    def process_bytes(
        self,
        content_bytes: bytes,
        *,
        filename: str = "",
        mime_type: str = "",
        metadata: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> KnowledgeDocument:
        if len(content_bytes) > MAX_DOCUMENT_SIZE_BYTES:
            raise StorageError(
                f"Conteúdo excede o limite máximo permitido de "
                f"{MAX_DOCUMENT_SIZE_BYTES // (1024 * 1024)} MiB."
            )

        processor = self.get_processor(file_path=filename, mime_type=mime_type, file_bytes=content_bytes)
        if processor is None:
            processor = TextProcessor()

        return processor.process_bytes(
            content_bytes,
            filename=filename,
            mime_type=mime_type,
            metadata=metadata,
            options=options,
        )


def default_processor_registry() -> DocumentProcessorRegistry:
    """Build default registry with all built-in document processors."""
    return DocumentProcessorRegistry(
        [
            PdfProcessor(),
            SpreadsheetProcessor(),
            WordProcessor(),
            PresentationProcessor(),
            EbookProcessor(),
            HtmlProcessor(),
            ImageProcessor(),
            TextProcessor(),
        ]
    )


_GLOBAL_REGISTRY: DocumentProcessorRegistry | None = None


def get_global_processor_registry() -> DocumentProcessorRegistry:
    global _GLOBAL_REGISTRY
    if _GLOBAL_REGISTRY is None:
        _GLOBAL_REGISTRY = default_processor_registry()
    return _GLOBAL_REGISTRY
