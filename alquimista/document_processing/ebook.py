from __future__ import annotations

import hashlib
import io
import posixpath
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

from bs4 import BeautifulSoup
from markdownify import markdownify

from ..errors import DocumentProcessingError
from ..markdown import normalize_markdown
from ..models import KnowledgeDocument
from .base import DocumentProcessor

_MAX_EPUB_UNCOMPRESSED_BYTES = 500 * 1024 * 1024
_DC = "{http://purl.org/dc/elements/1.1/}"


def _read_epub(content_bytes: bytes) -> tuple[str, str, str, list[str]]:
    """Return title, author, language and spine-ordered XHTML chapters of an EPUB."""
    with zipfile.ZipFile(io.BytesIO(content_bytes)) as archive:
        if sum(info.file_size for info in archive.infolist()) > _MAX_EPUB_UNCOMPRESSED_BYTES:
            raise ValueError("conteúdo descompactado excede o limite permitido")
        container = ElementTree.fromstring(archive.read("META-INF/container.xml"))
        rootfile = next(el for el in container.iter() if el.tag.endswith("rootfile"))
        opf_path = rootfile.attrib["full-path"]
        opf = ElementTree.fromstring(archive.read(opf_path))
        opf_dir = posixpath.dirname(opf_path)

        def dc(name: str) -> str:
            element = next(opf.iter(_DC + name), None)
            return (element.text or "").strip() if element is not None else ""

        manifest = {el.attrib.get("id"): el.attrib for el in opf.iter() if el.tag.endswith("}item")}
        chapters: list[str] = []
        for itemref in (el for el in opf.iter() if el.tag.endswith("}itemref")):
            item = manifest.get(itemref.attrib.get("idref"))
            if not item or "html" not in item.get("media-type", ""):
                continue
            href = posixpath.normpath(posixpath.join(opf_dir, item["href"]))
            chapters.append(archive.read(href).decode("utf-8", errors="replace"))
        return dc("title"), dc("creator"), dc("language"), chapters


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

        try:
            book_title, author, lang, chapters = _read_epub(content_bytes)
        except Exception as exc:
            raise DocumentProcessingError(f"Não foi possível processar o e-book {filename}: {exc}") from exc
        if book_title and not doc_metadata.get("title"):
            title = book_title
        ebook_meta = {"title": title, "author": author, "language": lang}

        for html_content in chapters:
            soup = BeautifulSoup(html_content, "html.parser")
            for tag in soup(["script", "style", "noscript", "nav"]):
                tag.decompose()
            chapter_text = markdownify(str(soup), heading_style="ATX", bullets="-").strip()
            if chapter_text:
                sections.append(chapter_text)

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
