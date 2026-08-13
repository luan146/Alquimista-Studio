from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import quote

from bs4 import BeautifulSoup

from .client import ConfluenceClient
from .models import KnowledgeDocument, MarkdownOptions, SourceConfig


def normalize_markdown(text: str) -> str:
    value = unicodedata.normalize("NFC", text or "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = "\n".join(line.rstrip() for line in value.splitlines())
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def format_updated_at(value: str | None) -> str:
    """Format Confluence timestamps as DD/MM/YYYY HH:MM."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return str(value)


def sha256_text(text: str) -> str:
    return hashlib.sha256(normalize_markdown(text).encode("utf-8")).hexdigest()


def _normalize_ancestors(value: Any) -> list[dict[str, str]]:
    """Keep only the stable ancestor fields required by ``ManifestEntry``."""
    if not isinstance(value, list):
        return []

    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        ancestor_id = item.get("id")
        title = item.get("title")
        if isinstance(ancestor_id, (dict, list)) or isinstance(title, (dict, list)):
            continue
        id_text = str(ancestor_id).strip() if ancestor_id is not None else ""
        title_text = str(title).strip() if title is not None else ""
        if not id_text or not title_text:
            continue
        normalized.append({"id": id_text, "title": title_text})
    return normalized


def relative_ancestor_titles(page: dict[str, Any], root_id: str) -> list[str]:
    ancestors = page.get("ancestors", []) or []
    ids = [str(item.get("id", "")) for item in ancestors]
    if root_id in ids:
        ancestors = ancestors[ids.index(root_id) + 1 :]
    elif str(page.get("id")) == root_id:
        ancestors = []
    return [str(item.get("title", "Sem título")) for item in ancestors]


def page_metadata(
    page: dict[str, Any], source: SourceConfig, root: dict[str, Any]
) -> dict[str, Any]:
    root_id = str(root["id"])
    trail = relative_ancestor_titles(page, root_id)
    version_value = page.get("version", {})
    version: dict[str, Any] = version_value if isinstance(version_value, dict) else {}
    space = page.get("space", {}) or root.get("space", {}) or {}
    author_value = version.get("by")
    author_data: dict[str, Any] = author_value if isinstance(author_value, dict) else {}
    labels = [
        str(item.get("name"))
        for item in page.get("metadata", {}).get("labels", {}).get("results", []) or []
        if item.get("name")
    ]
    title = str(page.get("title") or "Sem título")
    path = [str(root.get("title") or source.root_value), *trail, title]
    path = [value for index, value in enumerate(path) if value and (index == 0 or value != path[index - 1])]
    return {
        "source_id": source.id,
        "source_name": source.name,
        "space_key": str(space.get("key") or source.space_key),
        "space_name": str(space.get("name") or source.space_name),
        "root_page_id": root_id,
        "root_title": str(root.get("title") or source.root_value),
        "page_id": str(page["id"]),
        "document_key": f"{source.id}:{page['id']}",
        "title": title,
        "module": trail[0] if trail else ("Página raiz" if str(page["id"]) == root_id else title),
        "submodule": trail[1] if len(trail) > 1 else "",
        "path": path,
        "ancestors": [
            {"id": str(item.get("id", "")), "title": str(item.get("title", ""))}
            for item in page.get("ancestors", []) or []
        ],
        "source_url": ConfluenceClient.source_url(source.base_url, page),
        "confluence_version": version.get("number"),
        "updated_at": version.get("when"),
        "author": str(author_data.get("displayName") or author_data.get("username") or ""),
        "labels": labels,
    }


class MarkdownTransformer:
    def __init__(
        self,
        client: Any,
        source: SourceConfig,
        root: dict[str, Any],
        options: MarkdownOptions,
        translator: Callable[[str], str] | None = None,
    ) -> None:
        self.client = client
        self.source = source
        self.root = root
        self.options = options
        self.translator = translator or (lambda value: value)

    def _t(self, value: str) -> str:
        return self.translator(value)

    def _attachment_url(self, page_id: str, filename: str) -> str:
        return (
            f"{self.client.base_url}/download/attachments/{page_id}/"
            f"{quote(filename, safe='')}"
        )

    def _replace_links(self, soup: BeautifulSoup, page_id: str) -> None:
        for link in list(soup.find_all("ac:link")):
            page_ref = link.find("ri:page")
            attachment = link.find("ri:attachment")
            body = link.find(["ac:plain-text-link-body", "ac:link-body"])
            label = body.get_text(" ", strip=True) if body else ""
            anchor = soup.new_tag("a")
            if page_ref:
                target = str(page_ref.get("ri:content-title") or label or self._t("Página"))
                anchor["href"] = (
                    f"{self.client.base_url}/pages/viewpage.action?"
                    f"title={quote(target)}"
                )
                anchor.string = label or target
            elif attachment and attachment.get("ri:filename"):
                filename = str(attachment["ri:filename"])
                if not self.options.include_attachments:
                    link.decompose()
                    continue
                anchor["href"] = self._attachment_url(page_id, filename)
                anchor.string = label or filename
            else:
                anchor["href"] = "#"
                anchor.string = label or self._t("Link do Confluence")
            link.replace_with(anchor)

    def _replace_macros(self, soup: BeautifulSoup, page_id: str) -> None:
        for image in list(soup.find_all("ac:image")):
            if not self.options.include_images:
                image.decompose()
                continue
            attachment = image.find("ri:attachment")
            remote = image.find("ri:url")
            filename = str(attachment.get("ri:filename")) if attachment else ""
            src = (
                self._attachment_url(page_id, filename)
                if filename
                else str(remote.get("ri:value") or "") if remote else ""
            )
            if not src:
                image.decompose()
                continue
            rendered = soup.new_tag("img", src=src)
            if self.options.include_image_alt_text:
                rendered["alt"] = str(image.get("ac:alt") or filename or "Imagem")
            image.replace_with(rendered)

        self._replace_links(soup, page_id)
        for attachment in list(soup.find_all("ri:attachment")):
            if not self.options.include_attachments:
                attachment.decompose()
                continue
            filename = str(attachment.get("ri:filename") or "Anexo")
            anchor = soup.new_tag("a", href=self._attachment_url(page_id, filename))
            anchor.string = filename
            attachment.replace_with(anchor)

        for macro in list(soup.find_all("ac:structured-macro")):
            name = str(macro.get("ac:name") or "").casefold()
            rich = macro.find("ac:rich-text-body")
            plain = macro.find("ac:plain-text-body")
            wrapper = soup.new_tag("div")
            if name == "code":
                if not self.options.include_code_blocks:
                    macro.decompose()
                    continue
                pre = soup.new_tag("pre")
                code = soup.new_tag("code")
                code.string = plain.get_text("\n", strip=False) if plain else macro.get_text("\n")
                pre.append(code)
                macro.replace_with(pre)
                continue
            labels = {
                "warning": self._t("⚠ Aviso"),
                "info": self._t("ℹ Informação"),
                "note": self._t("📝 Observação"),
                "tip": self._t("💡 Dica"),
            }
            if name in labels and not self.options.include_panels:
                macro.decompose()
                continue
            if name == "expand" and not self.options.include_expand_macros:
                macro.decompose()
                continue
            if name in labels:
                strong = soup.new_tag("strong")
                strong.string = f"{labels[name]}:"
                wrapper.append(strong)
                wrapper.append(" ")
            elif name == "expand":
                title = macro.find("ac:parameter", attrs={"ac:name": "title"})
                strong = soup.new_tag("strong")
                strong.string = self._t("Conteúdo expansível — {title}:").format(
                    title=title.get_text(strip=True) if title else self._t("Detalhes")
                )
                wrapper.append(strong)
                wrapper.append(" ")
            elif not self.options.include_content_macros:
                macro.decompose()
                continue
            body = rich or plain
            if body:
                for child in list(body.contents):
                    wrapper.append(child.extract())
            else:
                em = soup.new_tag("em")
                em.string = self._t("Macro do Confluence: {name}").format(
                    name=name or self._t("desconhecida")
                )
                wrapper.append(em)
            macro.replace_with(wrapper)

    def technical_markdown(self, page: dict[str, Any]) -> str:
        from .connectors.confluence_parser import ConfluenceDocumentParser

        return ConfluenceDocumentParser(
            self.source,
            self.options,
            translator=self.translator,
        ).parse(page).content

    def hash_input(self, metadata: dict[str, Any], technical: str) -> str:
        if self.options.hash_scope == "content":
            return technical
        if self.options.hash_scope == "stable_metadata":
            stable = {
                "title": metadata["title"],
                "source": metadata["source_name"],
                "space": metadata["space_key"],
                "path": metadata["path"],
            }
            return json.dumps(stable, ensure_ascii=False, sort_keys=True) + "\n" + technical
        return f"{metadata['title']}\n{technical}"

    def full_document(
        self,
        metadata: dict[str, Any],
        technical: str,
        content_hash: str,
        collected_at: str,
        status: str,
    ) -> str:
        options = self.options
        fields = [
            ("page_id", self._t("ID da página"), metadata["page_id"], options.include_page_id),
            ("source_url", self._t("URL original"), metadata["source_url"], options.include_source_url),
            ("source_name", self._t("Fonte"), metadata["source_name"], options.include_source_name),
            ("space_key", self._t("Chave do espaço"), metadata["space_key"], options.include_space_key),
            ("space_name", self._t("Nome do espaço"), metadata["space_name"], options.include_space_name),
            ("root_title", self._t("Página raiz"), metadata["root_title"], options.include_root),
            ("module", self._t("Módulo"), metadata["module"], options.include_module),
            ("submodule", self._t("Submódulo"), metadata["submodule"], options.include_submodule),
            ("path", self._t("Caminho"), " > ".join(metadata["path"]), options.include_path),
            ("version", self._t("Versão no Confluence"), metadata["confluence_version"], options.include_version),
            ("updated_at", self._t("Última atualização"), format_updated_at(metadata["updated_at"]), options.include_updated_at),
            ("author", self._t("Autor"), metadata["author"], options.include_author),
            ("labels", self._t("Rótulos"), metadata["labels"], options.include_labels),
            ("content_hash", self._t("SHA-256"), content_hash, options.include_hash),
            ("collected_at", self._t("Data da coleta"), collected_at, options.include_collected_at),
            ("status", self._t("Status"), status, options.include_status),
        ]
        selected = [(key, label, value) for key, label, value, enabled in fields if enabled and value not in ("", None, [])]
        lines: list[str] = []
        marker_key = metadata["document_key"] if options.marker_include_ids else "document"
        if options.include_document_markers:
            lines.extend([f'<!-- ALQUIMISTA_DOCUMENT_START key="{marker_key}" -->', ""])
        if options.metadata_style in {"yaml", "both"}:
            lines.append("---")
            if options.include_title:
                lines.append(f"title: {json.dumps(metadata['title'], ensure_ascii=False)}")
            for key, _label, value in selected:
                lines.append(f"{key}: {json.dumps(value, ensure_ascii=False)}")
            lines.extend(["---", ""])
        if options.include_title:
            lines.extend([f"{'#' * options.title_heading_level} {metadata['title']}", ""])
        if options.metadata_style in {"markdown", "both"}:
            for key, label, value in selected:
                if key == "source_url":
                    rendered = f"[{self._t('Abrir no Confluence')}]({value})"
                elif isinstance(value, list):
                    rendered = ", ".join(str(item) for item in value)
                elif key in {"page_id", "content_hash"}:
                    rendered = f"`{value}`"
                else:
                    rendered = str(value)
                lines.append(f"**{label}:** {rendered}  ")
            if selected:
                lines.append("")
        if technical:
            if options.include_content_heading:
                level = min(6, options.title_heading_level + 1)
                heading = options.content_heading_text or self._t("Conteúdo")
                if heading == "Conteúdo técnico":
                    heading = self._t(heading)
                lines.extend([f"{'#' * level} {heading}", ""])
            lines.extend([technical, ""])
        if options.include_document_markers:
            lines.append(f'<!-- ALQUIMISTA_DOCUMENT_END key="{marker_key}" -->')
        return normalize_markdown("\n".join(lines)) + "\n"


def knowledge_document_metadata(
    document: KnowledgeDocument, source: SourceConfig
) -> dict[str, Any]:
    """Convert a normalized document to the manifest's stable metadata shape."""
    path = list(document.path or [document.title])
    container_key = str(document.metadata.get("space_key") or document.container_id)
    updated = document.updated_at.isoformat() if document.updated_at else None
    return {
        "source_id": source.id,
        "source_type": document.source_type,
        "source_name": source.name,
        "container_id": document.container_id,
        "container_type": "space" if document.source_type == "confluence_rest" else "container",
        "container_name": document.container_name,
        "document_id": document.id,
        "parent_id": document.parent_id,
        "page_id": document.id,
        "document_key": f"{source.id}:{document.container_id}:{document.id}",
        "title": document.title,
        "source_url": document.original_url,
        "space_key": container_key,
        "space_name": document.container_name,
        "root_page_id": "",
        "root_title": path[0] if path else document.title,
        "module": path[0] if len(path) > 1 else document.title,
        "submodule": path[1] if len(path) > 2 else "",
        "path": path,
        "ancestors": _normalize_ancestors(document.metadata.get("ancestors")),
        "confluence_version": document.metadata.get("confluence_version"),
        "author": document.metadata.get("author", ""),
        "labels": document.metadata.get("labels", []),
        "updated_at": updated,
        "etag": document.etag or document.metadata.get("etag"),
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "document_type": document.metadata.get("raw_type", "document"),
        "metadata": document.metadata,
    }


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
    ) -> "PreparedKnowledgeDocument":
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
        prepared: "PreparedKnowledgeDocument",
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
            ("updated_at", "Última atualização", format_updated_at(metadata["updated_at"]), options.include_updated_at),
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


@dataclass(frozen=True)
class PreparedKnowledgeDocument:
    """Canonical, deterministic input for final Markdown rendering."""

    metadata: dict[str, Any]
    content: str
    content_hash: str


def sample_page(translator: Callable[[str], str] | None = None) -> dict[str, Any]:
    translate = translator or (lambda value: value)
    return {
        "id": "123456",
        "title": translate("Como configurar uma venda"),
        "ancestors": [
            {"id": "100", "title": translate("Manual do Produto")},
            {"id": "110", "title": "POS"},
        ],
        "space": {"key": "EXEMPLO", "name": translate("Espaço de exemplo")},
        "version": {
            "number": 4,
            "when": "2026-07-26T15:00:00Z",
            "by": {"displayName": translate("Equipe de Produto")},
        },
        "metadata": {"labels": {"results": [{"name": translate("vendas")}]}},
        "body": {
            "storage": {
                "value": (
                    f"<p>{translate('Este é um exemplo de conteúdo técnico.')}</p>"
                    "<ac:structured-macro ac:name='tip'><ac:rich-text-body>"
                    f"<p>{translate('Revise os dados antes de concluir.')}</p>"
                    "</ac:rich-text-body></ac:structured-macro>"
                )
            }
        },
        "_links": {"webui": "/pages/viewpage.action?pageId=123456"},
    }
