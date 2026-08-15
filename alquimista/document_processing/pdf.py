from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

from ..markdown import normalize_markdown
from ..models import KnowledgeDocument
from .base import DocumentProcessor


class PdfProcessor(DocumentProcessor):
    """Processor for PDF files converting content into clean structured Markdown."""

    name = "pdf"
    supported_extensions = (".pdf",)
    supported_mimetypes = ("application/pdf", "application/x-pdf")

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
            mime_type="application/pdf",
            metadata=doc_metadata,
            options=options,
        )

    def process_bytes(
        self,
        content_bytes: bytes,
        *,
        filename: str = "",
        mime_type: str = "application/pdf",
        metadata: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> KnowledgeDocument:
        del mime_type
        doc_metadata = dict(metadata or {})
        doc_options = dict(options or {})
        doc_id = hashlib.sha256(content_bytes).hexdigest()
        title = doc_metadata.get("title") or Path(filename).stem or "Documento PDF"

        text_sections: list[str] = []
        pdf_meta: dict[str, Any] = {}
        page_count = 0

        # Attempt PyMuPDF (fitz) first
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(stream=content_bytes, filetype="pdf")
            try:
                page_count = len(doc)
                pdf_meta = {
                    "title": doc.metadata.get("title") or "",
                    "author": doc.metadata.get("author") or "",
                    "subject": doc.metadata.get("subject") or "",
                    "keywords": doc.metadata.get("keywords") or "",
                    "creator": doc.metadata.get("creator") or "",
                    "producer": doc.metadata.get("producer") or "",
                    "page_count": page_count,
                }
                if pdf_meta["title"] and not doc_metadata.get("title"):
                    title = str(pdf_meta["title"]).strip()

                for page_num in range(page_count):
                    page = doc[page_num]
                    page_text_blocks = page.get_text("blocks")
                    page_lines: list[str] = []

                    # Look for tables if available
                    tables: list[Any] = []
                    try:
                        tabs = page.find_tables()
                        tables = tabs.tables if tabs else []
                    except Exception:
                        tables = []

                    if tables:
                        for tab in tables:
                            df = tab.extract()
                            if df and len(df) > 0:
                                header = [str(col or "").strip() for col in df[0]]
                                rows = [[str(cell or "").strip() for cell in row] for row in df[1:]]
                                col_count = len(header)
                                if col_count > 0:
                                    table_md = [
                                        "| " + " | ".join(header) + " |",
                                        "| " + " | ".join(["---"] * col_count) + " |",
                                    ]
                                    for row in rows:
                                        padded = row + [""] * (col_count - len(row))
                                        table_md.append("| " + " | ".join(padded[:col_count]) + " |")
                                    page_lines.append("\n".join(table_md))
                    else:
                        for block in page_text_blocks:
                            text = block[4].strip()
                            if text:
                                # Clean up linebreaks inside sentences while preserving paragraph breaks
                                cleaned = "\n".join(
                                    line.strip() for line in text.splitlines() if line.strip()
                                )
                                if cleaned:
                                    page_lines.append(cleaned)

                    page_content = "\n\n".join(page_lines).strip()
                    if page_content:
                        if page_count > 1 and doc_options.get("include_page_headings", True):
                            text_sections.append(f"## Página {page_num + 1}\n\n{page_content}")
                        else:
                            text_sections.append(page_content)
            finally:
                doc.close()
        except ImportError:
            # Fallback to pypdf
            try:
                import pypdf

                reader = pypdf.PdfReader(io.BytesIO(content_bytes))
                page_count = len(reader.pages)
                info = reader.metadata or {}
                pdf_meta = {
                    "title": str(info.get("/Title") or ""),
                    "author": str(info.get("/Author") or ""),
                    "page_count": page_count,
                }
                if pdf_meta["title"] and not doc_metadata.get("title"):
                    title = str(pdf_meta["title"]).strip()

                for page_num, page in enumerate(reader.pages):
                    extracted = page.extract_text() or ""
                    extracted = extracted.strip()
                    if extracted:
                        if page_count > 1 and doc_options.get("include_page_headings", True):
                            text_sections.append(f"## Página {page_num + 1}\n\n{extracted}")
                        else:
                            text_sections.append(extracted)
            except Exception as exc:
                text_sections.append(f"*[Não foi possível extrair texto do PDF: {exc}]*")
        except Exception as exc:
            text_sections.append(f"*[Erro ao processar PDF: {exc}]*")

        markdown_body = "\n\n".join(text_sections).strip()
        full_content = normalize_markdown(markdown_body)

        doc_metadata.update(pdf_meta)
        doc_metadata.setdefault("raw_type", "pdf")
        doc_metadata.setdefault("page_count", page_count)
        doc_metadata.setdefault("filename", filename)

        return KnowledgeDocument(
            id=doc_id,
            container_id=str(doc_metadata.get("container_id") or "documents"),
            title=title,
            content=full_content,
            original_url=str(doc_metadata.get("original_url") or doc_metadata.get("file_path") or filename),
            source_type=str(doc_metadata.get("source_type") or "local_files"),
            container_name=str(doc_metadata.get("container_name") or "Documentos"),
            path=list(doc_metadata.get("path") or [title]),
            metadata=doc_metadata,
        )
