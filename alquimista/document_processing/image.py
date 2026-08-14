from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

from ..markdown import normalize_markdown
from ..models import KnowledgeDocument
from .base import DocumentProcessor


class ImageProcessor(DocumentProcessor):
    """Processor for images (PNG, JPG, WEBP, TIFF, BMP) with metadata and optional OCR."""

    name = "image"
    supported_extensions = (".png", ".jpg", ".jpeg", ".webp", ".tiff", ".bmp")
    supported_mimetypes = (
        "image/png",
        "image/jpeg",
        "image/webp",
        "image/tiff",
        "image/bmp",
    )

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
            mime_type="",
            metadata=doc_metadata,
            options=options,
        )

    def process_bytes(
        self,
        content_bytes: bytes,
        *,
        filename: str = "",
        mime_type: str = "",
        metadata: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> KnowledgeDocument:
        del mime_type, options
        doc_metadata = dict(metadata or {})
        doc_id = hashlib.sha256(content_bytes).hexdigest()
        title = doc_metadata.get("title") or Path(filename).stem or "Imagem"

        image_info: dict[str, Any] = {}
        ocr_text = ""

        try:
            from PIL import Image

            img = Image.open(io.BytesIO(content_bytes))
            image_info = {
                "width": img.width,
                "height": img.height,
                "format": img.format or "",
                "mode": img.mode,
            }

            # Optional OCR fallback if pytesseract is available
            try:
                import pytesseract

                ocr_text = pytesseract.image_to_string(img).strip()
            except Exception:
                ocr_text = ""

        except Exception as exc:
            image_info["error"] = str(exc)

        lines: list[str] = [
            f"![{title}]({doc_metadata.get('original_url') or doc_metadata.get('file_path') or filename})",
            "",
            f"**Dimensões:** {image_info.get('width', 0)}x{image_info.get('height', 0)}  ",
            f"**Formato:** {image_info.get('format', '')} ({image_info.get('mode', '')})  ",
        ]

        if ocr_text:
            lines.extend(["", "### Texto extraído (OCR)", "", ocr_text])

        content = normalize_markdown("\n".join(lines))
        doc_metadata.update(image_info)
        doc_metadata.setdefault("raw_type", "image")
        doc_metadata.setdefault("filename", filename)

        return KnowledgeDocument(
            id=doc_id,
            container_id=str(doc_metadata.get("container_id") or "images"),
            title=title,
            content=content,
            original_url=str(doc_metadata.get("original_url") or doc_metadata.get("file_path") or filename),
            source_type=str(doc_metadata.get("source_type") or "local_files"),
            container_name=str(doc_metadata.get("container_name") or "Imagens"),
            path=list(doc_metadata.get("path") or [title]),
            metadata=doc_metadata,
        )
