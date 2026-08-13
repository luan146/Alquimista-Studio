from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ..errors import AuthenticationError, InvalidResponseError
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


class ZendeskConfig(BaseModel):
    """Runtime-only Zendesk Help Center configuration."""

    model_config = ConfigDict(validate_assignment=True)

    subdomain: str
    access_token: SecretStr
    locale: str | None = None
    api_base_url: str | None = None
    page_size: int = Field(default=100, ge=1, le=100)

    @field_validator("subdomain")
    @classmethod
    def validate_subdomain(cls, value: str) -> str:
        value = value.strip().lower()
        if not value or any(char in value for char in "/?#."):
            raise ValueError("Informe somente o subdomínio Zendesk, sem https://.")
        return value

    @field_validator("locale")
    @classmethod
    def validate_locale(cls, value: str | None) -> str | None:
        value = value.strip() if value else None
        return value or None

    @property
    def base_url(self) -> str:
        return (self.api_base_url or f"https://{self.subdomain}.zendesk.com/api/v2").rstrip("/")


def _datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class ZendeskGuideConnector(KnowledgeSourceConnector):
    SOURCE_TYPE = "zendesk_guide"
    API_VERSION = "v2"

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
        if source.source_type != self.SOURCE_TYPE:
            raise ValueError("A configuração não pertence ao conector Zendesk Guide.")
        if not secret.strip():
            raise AuthenticationError("Informe um access token OAuth do Zendesk.")
        connector_options = source.connector_options
        subdomain = str(connector_options.get("subdomain") or source.space_key).strip()
        if not subdomain and source.base_url:
            hostname = urlparse(source.base_url).hostname or ""
            subdomain = hostname.split(".", 1)[0]
        self.source = source
        self.options = options
        self.markdown_options = markdown_options or MarkdownOptions()
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        api_base_url = str(connector_options.get("api_base_url") or source.base_url).rstrip("/") if (connector_options.get("api_base_url") or source.base_url) else None
        if api_base_url and not api_base_url.endswith("/api/v2"):
            api_base_url = f"{api_base_url}/api/v2"
        self.config = ZendeskConfig(
            subdomain=subdomain,
            access_token=SecretStr(secret),
            locale=str(connector_options.get("locale") or source.space_name) or None,
            api_base_url=api_base_url,
            page_size=int(connector_options.get("page_size", 100)),
        )
        self.client = client or ApiHttpClient(
            self.config.base_url,
            options,
            token=self.token,
            log=self.log,
            headers={"Authorization": f"Bearer {secret}"},
        )
        self._containers: dict[str, KnowledgeContainer] = {}
        self._documents: dict[tuple[str, str], dict[str, Any]] = {}

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name,
            base_url=self.config.base_url,
            connector_version=self.API_VERSION,
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_permissions=True,
            supports_updated_at=True,
            supports_bearer_token=True,
            supports_multiple_languages=True,
        )

    def _localized_path(self, resource: str) -> str:
        locale = quote(self.config.locale or "", safe="-")
        prefix = f"/help_center/{locale}" if locale else "/help_center"
        return f"{prefix}/{resource.lstrip('/')}"

    def _paged(
        self,
        path: str,
        key: str,
        *,
        params: dict[str, Any] | None = None,
        maximum: int = 5000,
        fail_on_truncate: bool = True,
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        next_path: str | None = path
        next_params = dict(params or {})
        next_params.setdefault("page[size]", self.config.page_size)
        seen: set[str] = set()
        while next_path and len(items) < maximum:
            marker = f"{next_path}?{sorted(next_params.items())}"
            if marker in seen:
                raise InvalidResponseError("A API do Zendesk repetiu o cursor de paginação.")
            seen.add(marker)
            data = self.client.get_json(next_path, params=next_params)
            if not isinstance(data, dict) or not isinstance(data.get(key, []), list):
                raise InvalidResponseError(f"A API do Zendesk retornou uma lista inválida ({key}).")
            items.extend(item for item in data[key] if isinstance(item, dict))
            links = data.get("links") or {}
            next_path = str(links.get("next") or "") or None
            # The official API returns an absolute next URL. Keep it opaque and
            # avoid accidentally duplicating query parameters from the cursor.
            next_params = {}
        if next_path and len(items) >= maximum and fail_on_truncate:
            raise InvalidResponseError(
                f"A API do Zendesk excedeu o limite de {maximum} itens para {key}; "
                "a coleção está incompleta e não foi importada."
            )
        return items[:maximum]

    def validate_connection(self) -> dict[str, Any]:
        categories = self._paged(
            self._localized_path("categories.json"),
            "categories",
            maximum=1,
            fail_on_truncate=False,
        )
        return {
            "subdomain": self.config.subdomain,
            "locale": self.config.locale or "default",
            "categories_visible": len(categories),
            "spaces_visible": len(categories),
            "auth_method": "OAuth access token (Bearer)",
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        result: list[KnowledgeContainer] = []
        categories = self._paged(self._localized_path("categories.json"), "categories")
        categories = self._ordered_items(categories)
        for category in categories:
            identifier = str(category.get("id") or "")
            if not identifier or category.get("draft"):
                continue
            container = KnowledgeContainer(
                id=identifier,
                key=identifier,
                name=str(category.get("name") or identifier),
                description=str(category.get("description") or "") or None,
                container_type="category",
                source_type=self.SOURCE_TYPE,
                updated_at=_datetime(category.get("updated_at")),
                metadata={
                    "locale": self.config.locale,
                    "original_url": category.get("html_url") or category.get("url") or "",
                    "position": category.get("position"),
                },
            )
            self._containers[identifier] = container
            result.append(container)
        return result

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        sections = self._paged(
            self._localized_path(f"categories/{quote(str(container_id), safe='')}/sections.json"),
            "sections",
        )
        sections = self._ordered_items(sections)
        documents: list[KnowledgeDocumentMetadata] = []
        category = self._containers.get(container_id)
        category_name = category.name if category else container_id
        for section in sections:
            section_id = str(section.get("id") or "")
            if not section_id or section.get("draft"):
                continue
            section_name = str(section.get("name") or section_id)
            articles = self._paged(
                self._localized_path(f"sections/{quote(section_id, safe='')}/articles.json"),
                "articles",
            )
            articles = self._ordered_items(articles)
            for article in articles:
                article_id = str(article.get("id") or "")
                if not article_id or article.get("draft") or article.get("outdated"):
                    continue
                raw = {
                    **article,
                    "_container_id": container_id,
                    "_section_id": section_id,
                    "_section_name": section_name,
                    "_category_name": category_name,
                }
                self._documents[(container_id, article_id)] = raw
                documents.append(self._metadata(raw))
        return documents

    def get_document(
        self, document_id: str, container_id: str | None = None
    ) -> KnowledgeDocument:
        key = (
            (str(container_id), str(document_id))
            if container_id and (str(container_id), str(document_id)) in self._documents
            else next((item for item in self._documents if item[1] == str(document_id)), None)
        )
        key = key or (str(container_id or "__default__"), str(document_id))
        raw = self.client.get_json(
            self._localized_path(f"articles/{quote(str(document_id), safe='')}.json"),
            params={"include": "translations"},
        )
        if not isinstance(raw, dict):
            raise InvalidResponseError("A API do Zendesk retornou um artigo inválido.")
        article_value = raw.get("article")
        article: dict[str, Any] = (
            dict(article_value) if isinstance(article_value, dict) else dict(raw)
        )
        merged = {
            **self._documents.get(key, {}),
            **article,
            "_container_id": key[0],
            "_etag": getattr(self.client, "last_response_headers", {}).get("etag"),
        }
        return self.normalize_document(merged)

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        return []

    @staticmethod
    def _ordered_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep API order, using Zendesk position when it is available."""
        if not any(item.get("position") is not None for item in items):
            return items
        return [
            item
            for _, item in sorted(
                enumerate(items),
                key=lambda pair: (
                    int(pair[1]["position"])
                    if isinstance(pair[1].get("position"), (int, str))
                    and str(pair[1]["position"]).isdigit()
                    else 2**31,
                    pair[0],
                ),
            )
        ]

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if not isinstance(raw_document, dict):
            raise TypeError("Documento bruto do Zendesk deve ser um objeto JSON.")
        metadata = self._metadata(raw_document)
        html = str(raw_document.get("body") or "")
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        content = markdownify(str(soup), heading_style="ATX", bullets="-").strip()
        container_id = str(raw_document["_container_id"])
        container = self._containers.get(container_id)
        return KnowledgeDocument(
            id=metadata.id,
            container_id=container_id,
            parent_id=metadata.parent_id,
            title=metadata.title,
            content=content,
            original_url=metadata.original_url,
            created_at=metadata.created_at,
            updated_at=metadata.updated_at,
            etag=metadata.etag,
            source_type=self.SOURCE_TYPE,
            container_name=container.name if container else str(raw_document.get("_category_name") or container_id),
            path=metadata.path,
            metadata={
                "locale": raw_document.get("locale") or self.config.locale,
                "section_id": raw_document.get("_section_id"),
                "section_name": raw_document.get("_section_name"),
                "position": raw_document.get("position"),
                "labels": raw_document.get("label_names") or [],
                "raw_type": "article",
                "etag": raw_document.get("_etag") or metadata.etag,
            },
        )

    def _metadata(self, article: dict[str, Any]) -> KnowledgeDocumentMetadata:
        container_id = str(article["_container_id"])
        article_id = str(article.get("id") or "")
        title = str(article.get("title") or article_id)
        section_name = str(article.get("_section_name") or "Seção")
        category_name = str(article.get("_category_name") or container_id)
        return KnowledgeDocumentMetadata(
            id=article_id,
            container_id=container_id,
            parent_id=str(article.get("_section_id") or "") or None,
            title=title,
            original_url=str(article.get("html_url") or article.get("url") or ""),
            created_at=_datetime(article.get("created_at")),
            updated_at=_datetime(article.get("updated_at")),
            etag=str(article.get("etag") or article.get("eTag") or "") or None,
            document_type="article",
            path=[category_name, section_name, title],
            metadata={
                "section_id": article.get("_section_id"),
                "section_name": section_name,
                "locale": article.get("locale") or self.config.locale,
                "position": article.get("position"),
                "visibility": article.get("visibility")
                or article.get("access")
                or (
                    "private"
                    if article.get("permission_group_id") or article.get("user_segment_id")
                    else "public"
                ),
                "ancestors": [
                    {"id": str(article.get("_section_id") or ""), "title": section_name}
                ],
            },
        )

    def close(self) -> None:
        session = getattr(self.client, "session", None)
        if session is not None:
            session.headers.pop("Authorization", None)
        self.client.close()
        self.secret = ""
        self.config.access_token = SecretStr("")
