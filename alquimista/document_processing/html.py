from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from markdownify import markdownify

from ..markdown import normalize_markdown
from ..models import KnowledgeDocument
from .base import DocumentProcessor


class HtmlProcessor(DocumentProcessor):
    """Processor for HTML files converting web/local pages to clean Markdown."""

    name = "html"
    supported_extensions = (".html", ".htm", ".xhtml")
    supported_mimetypes = ("text/html", "application/xhtml+xml")

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
            mime_type="text/html",
            metadata=doc_metadata,
            options=options,
        )

    def process_bytes(
        self,
        content_bytes: bytes,
        *,
        filename: str = "",
        mime_type: str = "text/html",
        metadata: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> KnowledgeDocument:
        del mime_type, options
        doc_metadata = dict(metadata or {})
        doc_id = hashlib.sha256(content_bytes).hexdigest()
        title = doc_metadata.get("title") or Path(filename).stem or "Página HTML"

        try:
            decoded = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            decoded = content_bytes.decode("latin-1", errors="replace")

        soup = BeautifulSoup(decoded, "html.parser")

        # Extract meta tags
        og_title = (
            soup.find("meta", property="og:title")
            or soup.find("meta", attrs={"name": "twitter:title"})
        )
        if og_title and isinstance(og_title.get("content"), str) and not doc_metadata.get("title"):
            title = str(og_title["content"]).strip()
        elif soup.title and soup.title.string and not doc_metadata.get("title"):
            title = str(soup.title.string).strip()

        # Remove non-content tags
        for tag in soup(["script", "style", "noscript", "template", "form", "svg", "canvas", "iframe", "nav", "footer", "aside"]):
            tag.decompose()

        main_candidates = (
            soup.find_all("article")
            or soup.find_all("main")
            or soup.find_all("div", attrs={"role": "main"})
            or soup.find_all("div", class_=re.compile(r"(content|article|post|document|markdown-body)", re.I))
        )
        root = main_candidates[0] if main_candidates else soup.body or soup

        markdown_text = markdownify(str(root), heading_style="ATX", bullets="-")
        content = normalize_markdown(markdown_text)

        doc_metadata.setdefault("raw_type", "html")
        doc_metadata.setdefault("filename", filename)

        return KnowledgeDocument(
            id=doc_id,
            container_id=str(doc_metadata.get("container_id") or "html_pages"),
            title=title,
            content=content,
            original_url=str(doc_metadata.get("original_url") or doc_metadata.get("file_path") or filename),
            source_type=str(doc_metadata.get("source_type") or "local_files"),
            container_name=str(doc_metadata.get("container_name") or "Páginas HTML"),
            path=list(doc_metadata.get("path") or [title]),
            metadata=doc_metadata,
        )
