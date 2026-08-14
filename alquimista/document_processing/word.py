from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path
from typing import Any

from ..markdown import normalize_markdown
from ..models import KnowledgeDocument
from .base import DocumentProcessor


def _extract_rtf_text(rtf_content: str) -> str:
    """Extract plain text from RTF content safely."""
    # Strip RTF control words and groups
    text = re.sub(r"\\(?:[a-zA-Z]+-?\d*|[^\r\n\t ])", "", rtf_content)
    text = re.sub(r"[{}]", "", text)
    return text.strip()


class WordProcessor(DocumentProcessor):
    """Processor for Word documents (DOCX, DOC, ODT, RTF) to clean Markdown."""

    name = "word"
    supported_extensions = (".docx", ".doc", ".odt", ".rtf")
    supported_mimetypes = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "application/vnd.oasis.opendocument.text",
        "application/rtf",
        "text/rtf",
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
        title = doc_metadata.get("title") or Path(filename).stem or "Documento Word"
        ext = Path(filename).suffix.lower() if filename else ".docx"

        sections: list[str] = []
        doc_props: dict[str, Any] = {}

        if ext == ".docx":
            try:
                import docx

                doc = docx.Document(io.BytesIO(content_bytes))
                core = doc.core_properties
                if core.title and not doc_metadata.get("title"):
                    title = core.title.strip()
                doc_props = {
                    "author": core.author or "",
                    "created": core.created.isoformat() if core.created else None,
                    "modified": core.modified.isoformat() if core.modified else None,
                    "comments": core.comments or "",
                }

                for child in doc.element.body:
                    tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if tag == "p":
                        # Match paragraph
                        p = docx.text.paragraph.Paragraph(child, doc)
                        text = p.text.strip()
                        if not text:
                            continue
                        style_name = p.style.name.lower() if p.style and p.style.name else ""
                        if "heading 1" in style_name:
                            sections.append(f"# {text}")
                        elif "heading 2" in style_name:
                            sections.append(f"## {text}")
                        elif "heading 3" in style_name:
                            sections.append(f"### {text}")
                        elif "heading 4" in style_name:
                            sections.append(f"#### {text}")
                        elif "list bullet" in style_name:
                            sections.append(f"- {text}")
                        elif "list number" in style_name:
                            sections.append(f"1. {text}")
                        else:
                            sections.append(text)
                    elif tag == "tbl":
                        # Match table
                        t = docx.table.Table(child, doc)
                        table_rows: list[list[str]] = []
                        for row in t.rows:
                            table_rows.append([cell.text.strip().replace("\n", " ").replace("|", "\\|") for cell in row.cells])
                        if table_rows:
                            col_count = len(table_rows[0])
                            table_md = [
                                "| " + " | ".join(table_rows[0]) + " |",
                                "| " + " | ".join(["---"] * col_count) + " |",
                            ]
                            for r in table_rows[1:]:
                                padded = r + [""] * (col_count - len(r))
                                table_md.append("| " + " | ".join(padded[:col_count]) + " |")
                            sections.append("\n".join(table_md))
            except Exception as exc:
                sections.append(f"*[Não foi possível processar documento DOCX: {exc}]*")

        elif ext in {".rtf"}:
            try:
                rtf_text = content_bytes.decode("utf-8", errors="replace")
                sections.append(_extract_rtf_text(rtf_text))
            except Exception as exc:
                sections.append(f"*[Erro ao ler RTF: {exc}]*")

        else:
            # Fallback for plain/binary text
            try:
                text = content_bytes.decode("utf-8", errors="replace")
                sections.append(text)
            except Exception as exc:
                sections.append(f"*[Erro ao ler arquivo: {exc}]*")

        full_content = normalize_markdown("\n\n".join(sections))
        doc_metadata.update(doc_props)
        doc_metadata.setdefault("raw_type", "word")
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
