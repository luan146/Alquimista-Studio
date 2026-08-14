from __future__ import annotations

import mimetypes
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..models import KnowledgeDocument


class DocumentProcessor(ABC):
    """Abstract contract for converting document file formats into normalized KnowledgeDocuments."""

    name: str = "base"
    supported_extensions: tuple[str, ...] = ()
    supported_mimetypes: tuple[str, ...] = ()

    def can_process(
        self,
        file_path: Path | str | None = None,
        mime_type: str | None = None,
        file_bytes: bytes | None = None,
    ) -> bool:
        del file_bytes
        if file_path:
            ext = Path(file_path).suffix.lower()
            if ext and ext in self.supported_extensions:
                return True
        if mime_type:
            mime = mime_type.lower().split(";")[0].strip()
            if mime in self.supported_mimetypes:
                return True
        if file_path:
            inferred_mime, _ = mimetypes.guess_type(str(file_path))
            if inferred_mime and inferred_mime.lower() in self.supported_mimetypes:
                return True
        return False

    @abstractmethod
    def process_file(
        self,
        file_path: Path | str,
        *,
        metadata: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> KnowledgeDocument:
        raise NotImplementedError

    @abstractmethod
    def process_bytes(
        self,
        content_bytes: bytes,
        *,
        filename: str = "",
        mime_type: str = "",
        metadata: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> KnowledgeDocument:
        raise NotImplementedError
