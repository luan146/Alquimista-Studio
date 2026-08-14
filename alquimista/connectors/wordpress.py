from __future__ import annotations

import base64
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


class WordPressConnector(KnowledgeSourceConnector):
    """Connector for WordPress sites via the official WP REST API v2."""

    SOURCE_TYPE = "wordpress_api"

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
            base_url = "https://wordpress.org"
        parsed = urlsplit(base_url)
        self.origin = f"{parsed.scheme}://{parsed.netloc}"

        if not parsed.path or parsed.path == "/":
            self.api_base = f"{self.origin}/wp-json/wp/v2"
        elif "wp-json" in parsed.path:
            self.api_base = base_url
        else:
            self.api_base = f"{base_url}/wp-json/wp/v2"

        self.source = source
        self.options = options
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)

        headers: dict[str, str] = {"Accept": "application/json"}
        if source.username and secret.strip():
            auth_str = f"{source.username}:{secret}"
            encoded = base64.b64encode(auth_str.encode("utf-8")).decode("utf-8")
            headers["Authorization"] = f"Basic {encoded}"
        elif secret.strip():
            headers["Authorization"] = f"Bearer {secret}"

        # ApiHttpClient connects to origin
        self.client = client or ApiHttpClient(
            self.origin,
            options,
            token=self.token,
            log=self.log,
            headers=headers,
        )
        self.api_path = urlsplit(self.api_base).path

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or "WordPress",
            base_url=self.api_base,
            connector_version="v2",
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_public_access=True,
            supports_bearer_token=True,
            supports_updated_at=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        data = self.client.get_json(self.api_path)
        return {
            "name": data.get("name", "WordPress Site"),
            "description": data.get("description", ""),
            "home": data.get("home") or data.get("url") or self.origin,
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        return [
            KnowledgeContainer(
                id="posts",
                key="posts",
                name="Posts / Artigos",
                description="Artigos do blog e posts de conteúdo",
                container_type="posts",
                source_type=self.SOURCE_TYPE,
            ),
            KnowledgeContainer(
                id="pages",
                key="pages",
                name="Páginas Institucionais / Documentação",
                description="Páginas estáticas do WordPress",
                container_type="pages",
                source_type=self.SOURCE_TYPE,
            ),
        ]

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []
        endpoint = f"{self.api_path}/{container_id}"
        try:
            items = self.client.get_json(endpoint, params={"per_page": 100})
            if isinstance(items, list):
                for item in items:
                    pid = str(item.get("id"))
                    title_obj = item.get("title") or {}
                    title = str(title_obj.get("rendered") or f"Documento #{pid}")
                    # Strip html tags from title
                    title = BeautifulSoup(title, "html.parser").get_text(" ", strip=True)
                    documents.append(
                        KnowledgeDocumentMetadata(
                            id=pid,
                            container_id=container_id,
                            title=title,
                            original_url=str(item.get("link") or ""),
                            created_at=_datetime(item.get("date_gmt") or item.get("date")),
                            updated_at=_datetime(item.get("modified_gmt") or item.get("modified")),
                            document_type=container_id[:-1] if container_id.endswith("s") else container_id,
                            path=[container_id, title],
                            metadata=item,
                        )
                    )
        except Exception as exc:
            self.log(f"Erro ao listar {container_id} no WordPress: {exc}")

        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        endpoint_type = container_id or "posts"
        endpoint = f"{self.api_path}/{endpoint_type}/{quote(document_id, safe='')}"
        item = self.client.get_json(endpoint)
        if not isinstance(item, dict):
            item = {}

        title_obj = item.get("title") or {}
        title = BeautifulSoup(str(title_obj.get("rendered") or f"Documento #{document_id}"), "html.parser").get_text(" ", strip=True)

        content_obj = item.get("content") or {}
        html = str(content_obj.get("rendered") or "")
        content = normalize_markdown(markdownify(html, heading_style="ATX", bullets="-"))

        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or "posts",
            title=title,
            content=content,
            original_url=str(item.get("link") or ""),
            source_type=self.SOURCE_TYPE,
            container_name="Posts" if container_id == "posts" else "Páginas",
            created_at=_datetime(item.get("date_gmt") or item.get("date")),
            updated_at=_datetime(item.get("modified_gmt") or item.get("modified")),
            path=[container_id or "posts", title],
            metadata=item,
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if isinstance(raw_document, dict):
            return KnowledgeDocument.model_validate(raw_document)
        raise TypeError("Documento bruto do WordPress deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        self.secret = ""
        self.client.close()

