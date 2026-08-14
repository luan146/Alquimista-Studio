from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from ..markdown import normalize_markdown
from ..models import KnowledgeDocument
from .base import DocumentProcessor


class TextProcessor(DocumentProcessor):
    """Processor for plain text and Markdown files (TXT, MD, MDX, RST)."""

    name = "text"
    supported_extensions = (".txt", ".md", ".markdown", ".mdx", ".rst")
    supported_mimetypes = ("text/plain", "text/markdown", "text/x-rst")

    def process_file(
        self,
        file_path: Path | str,
        *,
        metadata: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> KnowledgeDocument:
        path = Path(file_path)
        content_bytes = path.read_bytes()
        doc_metadata = dict(metadata or {})
        doc_metadata.setdefault("file_path", str(path.resolve()))
        doc_metadata.setdefault("filename", path.name)
        return self.process_bytes(
            content_bytes,
            filename=path.name,
            mime_type="text/plain",
            metadata=doc_metadata,
            options=options,
        )

    def process_bytes(
        self,
        content_bytes: bytes,
        *,
        filename: str = "",
        mime_type: str = "text/plain",
        metadata: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> KnowledgeDocument:
        del mime_type, options
        doc_metadata = dict(metadata or {})
        doc_id = hashlib.sha256(content_bytes).hexdigest()
        title = doc_metadata.get("title") or Path(filename).stem or "Texto"

        try:
            text = content_bytes.decode("utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                text = content_bytes.decode("latin-1", errors="replace")

        # If title was not explicitly given, try to extract first H1
        if not doc_metadata.get("title"):
            for line in text.splitlines():
                stripped = line.strip()
                if stripped.startswith("# ") and len(stripped) > 2:
                    title = stripped[2:].strip()
                    break

        content = normalize_markdown(text)
        doc_metadata.setdefault("raw_type", "text")
        doc_metadata.setdefault("filename", filename)

        return KnowledgeDocument(
            id=doc_id,
            container_id=str(doc_metadata.get("container_id") or "text_files"),
            title=title,
            content=content,
            original_url=str(doc_metadata.get("original_url") or doc_metadata.get("file_path") or filename),
            source_type=str(doc_metadata.get("source_type") or "local_files"),
            container_name=str(doc_metadata.get("container_name") or "Arquivos de Texto"),
            path=list(doc_metadata.get("path") or [title]),
            metadata=doc_metadata,
        )
