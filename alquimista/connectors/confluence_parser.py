from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import quote, urljoin

from bs4 import BeautifulSoup, Comment
from markdownify import markdownify

from ..client import ConfluenceClient
from ..markdown import normalize_markdown
from ..models import KnowledgeDocument, MarkdownOptions, SourceConfig


class ConfluenceDocumentParser:
    """Pure Confluence storage-format parser.

    HTTP, authentication and Qt are deliberately outside this component.  It
    converts a raw Confluence page into the canonical ``KnowledgeDocument``
    consumed by the shared extraction pipeline.
    """

    def __init__(
        self,
        source: SourceConfig,
        options: MarkdownOptions,
        translator: Callable[[str], str] | None = None,
    ) -> None:
        self.source = source
        self.options = options
        self.translator = translator or (lambda value: value)

    def _t(self, value: str) -> str:
        return self.translator(value)

    def _attachment_url(self, page_id: str, filename: str) -> str:
        return (
            f"{self.source.base_url}/download/attachments/{page_id}/"
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
                    f"{self.source.base_url}/pages/viewpage.action?"
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

    def parse_content(self, page_id: str, html: str) -> tuple[str, list[dict[str, str]]]:
        soup = BeautifulSoup(html, "html.parser")
        attachments = [
            {
                "filename": str(node.get("ri:filename") or node.get("filename") or ""),
                "url": self._attachment_url(page_id, str(node.get("ri:filename") or node.get("filename") or "")),
            }
            for node in soup.find_all("ri:attachment")
            if node.get("ri:filename") or node.get("filename")
        ]
        if self.options.remove_html_comments:
            for comment in soup.find_all(string=lambda value: isinstance(value, Comment)):
                comment.extract()
        if self.options.remove_noise:
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            for selector in (
                ".page-metadata", ".page-actions", ".content-byline", "#breadcrumbs",
                ".labels-section", ".comment-threads", "#comments-section", ".page-tree",
                ".plugin_pagetree",
            ):
                for element in soup.select(selector):
                    element.decompose()
        page_id = str(page_id)
        self._replace_macros(soup, page_id)
        if not self.options.include_images:
            for image in soup.find_all("img"):
                image.decompose()
        if not self.options.include_tables:
            for table in soup.find_all("table"):
                table.replace_with(table.get_text(" | ", strip=True))
        if not self.options.include_videos:
            for item in soup.find_all(["iframe", "video"]):
                item.decompose()
        if not self.options.include_links:
            for anchor in soup.find_all("a"):
                anchor.unwrap()
        if self.options.absolute_links:
            for tag in soup.find_all(True):
                for attribute in ("href", "src"):
                    value = tag.get(attribute)
                    if isinstance(value, str) and value.startswith("/"):
                        tag[attribute] = urljoin(
                            self.source.base_url + "/", value.lstrip("/")
                        )
        return normalize_markdown(markdownify(str(soup), heading_style="ATX", bullets="-")), attachments

    def parse(self, raw_document: Mapping[str, Any]) -> KnowledgeDocument:
        container = raw_document.get("space") or {}
        container_id = str(
            raw_document.get("container_id") or container.get("key") or self.source.space_key
        )
        page_id = str(raw_document.get("id", ""))
        ancestors = raw_document.get("ancestors", []) or []
        titles = [str(item.get("title") or "") for item in ancestors if isinstance(item, dict) and item.get("title")]
        version = raw_document.get("version") or {}
        author = version.get("by") or {}
        labels = [
            str(item.get("name"))
            for item in (raw_document.get("metadata", {}).get("labels", {}).get("results", []) or [])
            if isinstance(item, dict) and item.get("name")
        ]
        content, attachments = self.parse_content(
            page_id, str(raw_document.get("body", {}).get("storage", {}).get("value") or "")
        )
        return KnowledgeDocument(
            id=page_id,
            container_id=container_id,
            parent_id=str(ancestors[-1].get("id")) if ancestors else None,
            title=str(raw_document.get("title") or "Sem título"),
            content=content.strip(),
            original_url=ConfluenceClient.source_url(self.source.base_url, dict(raw_document)),
            updated_at=_datetime(version.get("when")),
            source_type="confluence_rest",
            container_name=str(container.get("name") or container_id),
            path=[*titles, str(raw_document.get("title") or "Sem título")],
            attachments=attachments,
            metadata={
                "confluence_version": version.get("number"),
                "author": str(author.get("displayName") or author.get("username") or ""),
                "labels": labels,
                "ancestors": ancestors,
                "raw_type": raw_document.get("type", "page"),
                "space_key": container_id,
                "space_name": str(container.get("name") or container_id),
            },
        )


def _datetime(value: object):
    from datetime import datetime

    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
