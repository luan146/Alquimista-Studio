from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from markdownify import markdownify

from ..markdown import normalize_markdown
from ..models import KnowledgeDocument
from .base import DocumentProcessor


class EbookProcessor(DocumentProcessor):
    """Processor for EPUB ebooks converting chapters into clean structured Markdown."""

    name = "ebook"
    supported_extensions = (".epub",)
    supported_mimetypes = ("application/epub+zip",)

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
            mime_type="application/epub+zip",
            metadata=doc_metadata,
            options=options,
        )

    def process_bytes(
        self,
        content_bytes: bytes,
        *,
        filename: str = "",
        mime_type: str = "application/epub+zip",
        metadata: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> KnowledgeDocument:
        del mime_type, options
        doc_metadata = dict(metadata or {})
        doc_id = hashlib.sha256(content_bytes).hexdigest()
        title = doc_metadata.get("title") or Path(filename).stem or "E-book"

        sections: list[str] = []
        ebook_meta: dict[str, Any] = {}

        try:
            import ebooklib
            from ebooklib import epub

            # Create a temporary BytesIO or write to temp file since read_epub accepts path or BytesIO in newer versions
            # ebooklib epub.read_epub accepts file path or bytes/file-like
            book = epub.read_epub(io.BytesIO(content_bytes))

            meta_title = book.get_metadata("DC", "title")
            if meta_title and not doc_metadata.get("title"):
                title = str(meta_title[0][0]) if meta_title[0] else title

            creator = book.get_metadata("DC", "creator")
            author = str(creator[0][0]) if creator and creator[0] else ""
            language = book.get_metadata("DC", "language")
            lang = str(language[0][0]) if language and language[0] else ""

            ebook_meta = {
                "title": title,
                "author": author,
                "language": lang,
            }

            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    html_content = item.get_content().decode("utf-8", errors="replace")
                    soup = BeautifulSoup(html_content, "html.parser")
                    for tag in soup(["script", "style", "noscript", "nav"]):
                        tag.decompose()
                    chapter_text = markdownify(str(soup), heading_style="ATX", bullets="-").strip()
                    if chapter_text:
                        sections.append(chapter_text)

        except Exception as exc:
            sections.append(f"*[Não foi possível processar e-book: {exc}]*")

        full_content = normalize_markdown("\n\n---\n\n".join(sections))
        doc_metadata.update(ebook_meta)
        doc_metadata.setdefault("raw_type", "ebook")
        doc_metadata.setdefault("filename", filename)

        return KnowledgeDocument(
            id=doc_id,
            container_id=str(doc_metadata.get("container_id") or "ebooks"),
            title=title,
            content=full_content,
            original_url=str(doc_metadata.get("original_url") or doc_metadata.get("file_path") or filename),
            source_type=str(doc_metadata.get("source_type") or "local_files"),
            container_name=str(doc_metadata.get("container_name") or "E-books"),
            path=list(doc_metadata.get("path") or [title]),
            metadata=doc_metadata,
        )
