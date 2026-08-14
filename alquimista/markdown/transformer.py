from __future__ import annotations

import json
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from bs4 import BeautifulSoup

from .normalization import format_updated_at, normalize_markdown

if TYPE_CHECKING:
    from ..models import MarkdownOptions, SourceConfig


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
                else str(remote.get("ri:value") or "")
                if remote
                else ""
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
        from ..connectors.confluence_parser import ConfluenceDocumentParser

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
            (
                "source_url",
                self._t("URL original"),
                metadata["source_url"],
                options.include_source_url,
            ),
            ("source_name", self._t("Fonte"), metadata["source_name"], options.include_source_name),
            ("space_key", self._t("Chave do espaço"), metadata["space_key"], options.include_space_key),
            ("space_name", self._t("Nome do espaço"), metadata["space_name"], options.include_space_name),
            ("root_title", self._t("Página raiz"), metadata["root_title"], options.include_root),
            ("module", self._t("Módulo"), metadata["module"], options.include_module),
            ("submodule", self._t("Submódulo"), metadata["submodule"], options.include_submodule),
            ("path", self._t("Caminho"), " > ".join(metadata["path"]), options.include_path),
            ("version", self._t("Versão no Confluence"), metadata["confluence_version"], options.include_version),
            (
                "updated_at",
                self._t("Última atualização"),
                format_updated_at(metadata["updated_at"]),
                options.include_updated_at,
            ),
            ("author", self._t("Autor"), metadata["author"], options.include_author),
            ("labels", self._t("Rótulos"), metadata["labels"], options.include_labels),
            ("content_hash", self._t("SHA-256"), content_hash, options.include_hash),
            ("collected_at", self._t("Data da coleta"), collected_at, options.include_collected_at),
            ("status", self._t("Status"), status, options.include_status),
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


__all__ = ["MarkdownTransformer"]
