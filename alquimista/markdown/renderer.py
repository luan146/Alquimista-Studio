from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .metadata import knowledge_document_metadata
from .normalization import format_updated_at, normalize_markdown, sha256_text

if TYPE_CHECKING:
    from ..models import KnowledgeDocument, MarkdownOptions, SourceConfig


@dataclass(frozen=True)
class PreparedKnowledgeDocument:
    """Canonical, deterministic input for final Markdown rendering."""

    metadata: dict[str, Any]
    content: str
    content_hash: str


class KnowledgeDocumentRenderer:
    """Platform-neutral Markdown renderer for normalized documents."""

    def __init__(self, options: MarkdownOptions) -> None:
        self.options = options

    def prepare(
        self,
        document: KnowledgeDocument,
        source: SourceConfig,
        *,
        metadata_overrides: dict[str, Any] | None = None,
    ) -> PreparedKnowledgeDocument:
        """Prepare the canonical renderer input shared by preview and extraction."""
        metadata = knowledge_document_metadata(document, source)
        if metadata_overrides:
            metadata.update(metadata_overrides)
        content = normalize_markdown(document.content)
        content_hash = sha256_text(self.hash_input(metadata, content))
        return PreparedKnowledgeDocument(
            metadata=metadata,
            content=content,
            content_hash=content_hash,
        )

    def hash_input(self, metadata: dict[str, Any], content: str) -> str:
        if self.options.hash_scope == "content":
            return content
        if self.options.hash_scope == "stable_metadata":
            stable = {
                "title": metadata["title"],
                "source": metadata["source_name"],
                "container": metadata["container_id"],
                "path": metadata["path"],
            }
            return json.dumps(stable, ensure_ascii=False, sort_keys=True) + "\n" + content
        return f"{metadata['title']}\n{content}"

    def render(
        self,
        metadata: dict[str, Any],
        content: str,
        content_hash: str,
        collected_at: str,
        status: str,
    ) -> str:
        return self.render_prepared(
            PreparedKnowledgeDocument(metadata, content, content_hash),
            collected_at,
            status,
        )

    def render_prepared(
        self,
        prepared: PreparedKnowledgeDocument,
        collected_at: str,
        status: str,
    ) -> str:
        metadata = prepared.metadata
        content = prepared.content
        content_hash = prepared.content_hash
        options = self.options
        fields = [
            ("document_id", "ID do documento", metadata["document_id"], options.include_page_id),
            ("source_url", "URL original", metadata["source_url"], options.include_source_url),
            ("source_name", "Fonte", metadata["source_name"], options.include_source_name),
            ("container_id", "ID do contêiner", metadata["container_id"], options.include_space_key),
            ("container_name", "Contêiner", metadata["container_name"], options.include_space_name),
            ("root_title", "Página raiz", metadata.get("root_title", ""), options.include_root),
            ("module", "Módulo", metadata.get("module", ""), options.include_module),
            ("submodule", "Submódulo", metadata.get("submodule", ""), options.include_submodule),
            ("path", "Caminho", " > ".join(metadata["path"]), options.include_path),
            ("version", "Versão", metadata.get("confluence_version"), options.include_version),
            (
                "updated_at",
                "Última atualização",
                format_updated_at(metadata["updated_at"]),
                options.include_updated_at,
            ),
            ("author", "Autor", metadata["author"], options.include_author),
            ("labels", "Rótulos", metadata["labels"], options.include_labels),
            ("content_hash", "SHA-256", content_hash, options.include_hash),
            ("collected_at", "Data da coleta", collected_at, options.include_collected_at),
            ("status", "Status", status, options.include_status),
        ]
        selected = [
            (key, label, value)
            for key, label, value, enabled in fields
            if enabled and value not in ("", None, [])
        ]
        lines: list[str] = []
        marker_key = metadata["document_key"] if options.marker_include_ids else "document"
        if options.include_document_markers:
            lines.extend([f'<!-- ALQUIMISTA_DOCUMENT_START key="{marker_key}" -->', ""])
        if options.metadata_style in {"yaml", "both"}:
            lines.extend(["---", f"title: {json.dumps(metadata['title'], ensure_ascii=False)}"])
            for key, _label, value in selected:
                lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
            lines.extend(["---", ""])
        if options.include_title:
            lines.extend([f"{'#' * options.title_heading_level} {metadata['title']}", ""])
        if options.metadata_style in {"markdown", "both"}:
            for key, label, value in selected:
                if key == "source_url":
                    rendered = f"[Abrir na origem]({value})"
                elif isinstance(value, list):
                    rendered = ", ".join(str(item) for item in value)
                elif key in {"document_id", "content_hash"}:
                    rendered = f"`{value}`"
                else:
                    rendered = str(value)
                lines.append(f"**{label}:** {rendered}  ")
            if selected:
                lines.append("")
        if content:
            if options.include_content_heading:
                level = min(6, options.title_heading_level + 1)
                lines.extend([f"{'#' * level} {options.content_heading_text or 'Conteúdo'}", ""])
            lines.extend([content, ""])
        if options.include_document_markers:
            lines.append(f'<!-- ALQUIMISTA_DOCUMENT_END key="{marker_key}" -->')
        return normalize_markdown("\n".join(lines)) + "\n"


__all__ = ["KnowledgeDocumentRenderer", "PreparedKnowledgeDocument"]
