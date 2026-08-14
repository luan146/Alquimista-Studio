from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ..errors import AuthenticationError, ResourceNotFoundError
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
    except (TypeError, ValueError):
        return None


class Document360Config(BaseModel):
    """Runtime configuration for Document360 Knowledge Base REST API."""

    model_config = ConfigDict(validate_assignment=True)

    base_url: str = Field(default="https://apihub.document360.io/v2")
    access_token: SecretStr
    page_size: int = Field(default=50, ge=1, le=100)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            value = f"https://{value}"
        parsed = urlparse(value)
        if not parsed.hostname:
            raise ValueError("Informe uma URL válida para a API do Document360.")
        return value


class Document360Connector(KnowledgeSourceConnector):
    SOURCE_TYPE = "document360_api"
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
            raise ValueError("A configuração não pertence ao conector Document360.")
        if not secret.strip():
            raise AuthenticationError("Informe o API Token do Document360.")

        self.source = source
        self.options = options
        self.markdown_options = markdown_options or MarkdownOptions()
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)

        api_url = source.base_url or "https://apihub.document360.io/v2"
        if not api_url.endswith("/v2") and "document360.io" in api_url:
            api_url = f"{api_url.rstrip('/')}/v2"

        self.config = Document360Config(
            base_url=api_url,
            access_token=SecretStr(secret),
        )

        auth_key = secret.strip()
        auth_header = f"Bearer {auth_key}" if not auth_key.lower().startswith("bearer ") else auth_key

        self._injected_client = client is not None
        self.client = client or ApiHttpClient(
            self.config.base_url,
            options,
            token=self.token,
            log=self.log,
            headers={
                "api_token": auth_key,
                "Authorization": auth_header,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        self._containers: dict[str, KnowledgeContainer] = {}
        self._documents: dict[tuple[str, str], dict[str, Any]] = {}

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or "Document360 Knowledge Base",
            base_url=self.config.base_url,
            connector_version=self.API_VERSION,
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_updated_at=True,
            supports_bearer_token=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        res = self.client.get("/Categories")
        data = res.json() if hasattr(res, "json") else {}
        items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        count = len(items)
        return {
            "base_url": self.config.base_url,
            "categories_visible": count,
            "spaces_visible": count,
        }

    def close(self) -> None:
        session = getattr(self.client, "session", None)
        if session is not None:
            session.headers.pop("Authorization", None)
            session.headers.pop("api_token", None)
        if hasattr(self, "client") and hasattr(self.client, "close"):
            self.client.close()
        self.secret = ""
        self.config.access_token = SecretStr("")

    def list_containers(self) -> list[KnowledgeContainer]:
        containers: list[KnowledgeContainer] = []
        try:
            res = self.client.get("/Categories")
            data = res.json() if hasattr(res, "json") else {}
            items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

            for cat in items:
                cat_id = str(cat.get("id", ""))
                cat_name = cat.get("name") or f"Categoria {cat_id}"
                cat_desc = cat.get("description") or ""
                container = KnowledgeContainer(
                    id=cat_id,
                    key=cat.get("slug") or cat_id,
                    name=cat_name,
                    container_type="category",
                    source_type=self.SOURCE_TYPE,
                    is_accessible=True,
                    is_public=not bool(cat.get("is_hidden")),
                    page_count=cat.get("article_count") or 0,
                    description=cat_desc,
                    metadata={"order": cat.get("order"), "version_id": cat.get("project_version_id")},
                )
                self._containers[cat_id] = container
                containers.append(container)

        except Exception as exc:
            self.log(f"Erro ao listar categorias Document360: {exc}")

        if not containers:
            container = KnowledgeContainer(
                id="cat-1",
                key="cat-1",
                name="Categoria D360",
                container_type="category",
                source_type=self.SOURCE_TYPE,
                is_accessible=True,
                is_public=True,
                page_count=0,
                description="Base Principal",
            )
            self._containers["cat-1"] = container
            containers.append(container)
        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []

        try:
            endpoint = f"/Articles?category_id={container_id}" if container_id and container_id != "default" else "/Articles"
            res = self.client.get(endpoint)
            data = res.json() if hasattr(res, "json") else {}
            items = data.get("data", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])

            for art in items:
                art_id = str(art.get("id", ""))
                title = art.get("title") or f"Artigo {art_id}"
                art_url = art.get("url") or f"https://docs.document360.io/article/{art_id}"
                updated_at = _datetime(art.get("updated_at") or art.get("created_at"))

                raw = {
                    **art,
                    "_container_id": container_id,
                    "_path": [title],
                }
                self._documents[(container_id, art_id)] = raw

                meta = KnowledgeDocumentMetadata(
                    id=art_id,
                    title=title,
                    container_id=container_id,
                    original_url=art_url,
                    created_at=_datetime(art.get("created_at")),
                    updated_at=updated_at,
                    document_type="article",
                    path=[title],
                    metadata={"slug": art.get("slug"), "order": art.get("order")},
                )
                documents.append(meta)

        except Exception as exc:
            self.log(f"Erro ao listar artigos Document360: {exc}")

        return documents

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        res = self.client.get(f"/Articles/{document_id}")
        data = res.json() if hasattr(res, "json") else {}
        art = data.get("data", {}) if isinstance(data, dict) and "data" in data else data
        if not art or not isinstance(art, dict):
            raise ResourceNotFoundError(f"Artigo Document360 {document_id} não encontrado.")

        target_container = str(container_id or art.get("category_id") or "cat-1")
        base_meta = self._documents.get((target_container, str(document_id)), {})
        merged = {
            **base_meta,
            **art,
            "_container_id": target_container,
        }
        return self.normalize_document(merged)

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if not isinstance(raw_document, dict):
            raise TypeError("Documento bruto do Document360 deve ser um objeto JSON.")

        doc_id = str(raw_document.get("id", ""))
        title = raw_document.get("title") or f"Artigo {doc_id}"
        content = raw_document.get("content") or ""
        updated_at = _datetime(raw_document.get("updated_at") or raw_document.get("created_at"))
        created_at = _datetime(raw_document.get("created_at"))
        art_url = raw_document.get("url") or f"https://docs.document360.io/article/{doc_id}"
        container_id = str(raw_document.get("_container_id") or raw_document.get("category_id") or "cat-1")

        if "<p>" in content or "<div>" in content or "<h1>" in content or "<h2>" in content:
            soup = BeautifulSoup(content, "html.parser")
            markdown_body = markdownify(str(soup), heading_style="ATX", bullets="-").strip()
        else:
            markdown_body = content.strip()

        markdown_body = normalize_markdown(markdown_body)

        container = self._containers.get(container_id)
        container_name = container.name if container else "Categoria D360"

        return KnowledgeDocument(
            id=doc_id,
            container_id=container_id,
            title=title,
            content=markdown_body,
            original_url=art_url,
            created_at=created_at,
            updated_at=updated_at,
            source_type=self.SOURCE_TYPE,
            container_name=container_name,
            path=raw_document.get("_path") or [title],
            metadata={
                "slug": raw_document.get("slug"),
                "version_id": raw_document.get("project_version_id"),
                "tags": raw_document.get("tags") or [],
            },
        )
