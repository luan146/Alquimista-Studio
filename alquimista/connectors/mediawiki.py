from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup
from markdownify import markdownify

from ..markdown import normalize_markdown
from ..models import (
    ConnectorCapabilities,
    ExtractionOptions,
    KnowledgeContainer,
    KnowledgeDocument,
    KnowledgeDocumentMetadata,
    KnowledgeSource,
    MarkdownOptions,
    SourceConfig,
)
from ..runtime import CancellationToken, LogCallback
from .base import KnowledgeSourceConnector
from .http import ApiHttpClient


def _datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


class MediaWikiConnector(KnowledgeSourceConnector):
    """Connector for MediaWiki instances (Wikipedia, Wikia, Enterprise MediaWiki) via api.php."""

    SOURCE_TYPE = "mediawiki_api"

    def __init__(
        self,
        source: SourceConfig,
        options: ExtractionOptions,
        *,
        secret: str = "",
        token: CancellationToken | None = None,
        log: LogCallback | None = None,
        client: ApiHttpClient | None = None,
        markdown_options: MarkdownOptions | None = None,
    ) -> None:
        del markdown_options
        base_url = source.base_url.rstrip("/")
        if not base_url:
            base_url = "https://pt.wikipedia.org/w/api.php"
        elif not base_url.endswith("api.php"):
            if base_url.endswith("/w"):
                base_url = f"{base_url}/api.php"
            else:
                base_url = f"{base_url}/w/api.php"

        self.source = source
        self.options = options
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        self.api_url = base_url

        parsed = urlsplit(self.api_url)
        self.origin = f"{parsed.scheme}://{parsed.netloc}"

        headers: dict[str, str] = {
            "Accept": "application/json",
            "User-Agent": "ALQuimista-Studio/3.0 (MediaWiki-Client)",
        }
        if secret.strip():
            headers["Authorization"] = f"Bearer {secret}"

        # ApiHttpClient expects base_url to be https origin
        self.client = client or ApiHttpClient(
            self.origin,
            options,
            token=self.token,
            log=self.log,
            headers=headers,
        )
        self.api_path = parsed.path or "/w/api.php"

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or "MediaWiki",
            base_url=self.api_url,
            connector_version="1.0",
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_public_access=True,
            supports_updated_at=True,
            supports_search=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        data = self.client.get_json(
            self.api_path,
            params={"action": "query", "meta": "siteinfo", "siprop": "general", "format": "json"},
        )
        general = (data.get("query") or {}).get("general") or {}
        return {
            "sitename": general.get("sitename", "MediaWiki"),
            "base": general.get("base", ""),
            "generator": general.get("generator", ""),
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        # Return Main Namespace container and Categories
        containers: list[KnowledgeContainer] = [
            KnowledgeContainer(
                id="main",
                key="main",
                name="Principal (Artigos)",
                container_type="namespace",
                source_type=self.SOURCE_TYPE,
            )
        ]
        try:
            data = self.client.get_json(
                self.api_path,
                params={"action": "query", "list": "allcategories", "aclimit": 50, "format": "json"},
            )
            cats = (data.get("query") or {}).get("allcategories") or []
            for cat in cats:
                name = str(cat.get("*") or "")
                if name:
                    containers.append(
                        KnowledgeContainer(
                            id=f"category_{name}",
                            key=f"category_{name}",
                            name=f"Categoria: {name}",
                            container_type="category",
                            source_type=self.SOURCE_TYPE,
                        )
                    )
        except Exception as exc:
            self.log(f"Erro ao listar categorias do MediaWiki: {exc}")
        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []
        params = {"action": "query", "format": "json", "aplimit": 100}

        if container_id.startswith("category_"):
            cat_name = container_id.replace("category_", "")
            params.update({"list": "categorymembers", "cmtitle": f"Category:{cat_name}", "cmlimit": 100})
        else:
            params.update({"list": "allpages", "apnamespace": 0})

        try:
            data = self.client.get_json(self.api_path, params=params)
            query_obj = data.get("query") or {}
            items = query_obj.get("allpages") or query_obj.get("categorymembers") or []
            for item in items:
                page_id = str(item.get("pageid"))
                title = str(item.get("title") or f"Página #{page_id}")
                documents.append(
                    KnowledgeDocumentMetadata(
                        id=page_id,
                        container_id=container_id,
                        title=title,
                        original_url=f"{self.origin}/wiki/{quote(title, safe='')}",
                        document_type="page",
                        path=[container_id, title],
                        metadata=item,
                    )
                )
        except Exception as exc:
            self.log(f"Erro ao listar páginas do MediaWiki: {exc}")

        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        data = self.client.get_json(
            self.api_path,
            params={
                "action": "parse",
                "pageid": document_id,
                "prop": "text|displaytitle|categories|revid",
                "format": "json",
            },
        )
        parse_data = (data.get("parse") or {}) if isinstance(data, dict) else {}
        title = str(parse_data.get("displaytitle") or parse_data.get("title") or f"Página #{document_id}")
        html = str((parse_data.get("text") or {}).get("*") or "")

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript", "div.navbox", "table.metadata"]):
            tag.decompose()

        content = normalize_markdown(markdownify(str(soup), heading_style="ATX", bullets="-"))
        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or "main",
            title=title,
            content=content,
            original_url=f"{self.origin}/wiki/{quote(title, safe='')}",
            source_type=self.SOURCE_TYPE,
            container_name=container_id or "MediaWiki",
            path=[container_id or "MediaWiki", title],
            metadata=parse_data,
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if isinstance(raw_document, dict):
            return KnowledgeDocument.model_validate(raw_document)
        raise TypeError("Documento bruto do MediaWiki deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        self.secret = ""
        self.client.close()

