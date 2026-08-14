from __future__ import annotations

import base64
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


class HelpScoutConfig(BaseModel):
    """Runtime configuration for Help Scout Docs REST API."""

    model_config = ConfigDict(validate_assignment=True)

    base_url: str = Field(default="https://docsapi.helpscout.net/v1")
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
            raise ValueError("Informe uma URL válida para a API Docs do Help Scout.")
        return value


class HelpScoutConnector(KnowledgeSourceConnector):
    SOURCE_TYPE = "helpscout_docs"
    API_VERSION = "v1"

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
            raise ValueError("A configuração não pertence ao conector Help Scout Docs.")
        if not secret.strip():
            raise AuthenticationError("Informe a API Key do Help Scout Docs.")

        self.source = source
        self.options = options
        self.markdown_options = markdown_options or MarkdownOptions()
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)

        api_url = source.base_url or "https://docsapi.helpscout.net/v1"
        if not api_url.endswith("/v1") and "helpscout.net" in api_url:
            api_url = f"{api_url.rstrip('/')}/v1"

        self.config = HelpScoutConfig(
            base_url=api_url,
            access_token=SecretStr(secret),
        )

        auth_key = secret.strip()
        if ":" not in auth_key and not auth_key.lower().startswith(("basic ", "bearer ")):
            auth_val = base64.b64encode(f"{auth_key}:X".encode("utf-8")).decode("ascii")
            auth_header = f"Basic {auth_val}"
        elif auth_key.lower().startswith(("basic ", "bearer ")):
            auth_header = auth_key
        else:
            auth_val = base64.b64encode(auth_key.encode("utf-8")).decode("ascii")
            auth_header = f"Basic {auth_val}"

        self._injected_client = client is not None
        self.client = client or ApiHttpClient(
            self.config.base_url,
            options,
            token=self.token,
            log=self.log,
            headers={
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
            name=self.source.name or "Help Scout Docs",
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
        res = self.client.get("/collections?page=1&pageSize=1")
        data = res.json() if hasattr(res, "json") else {}
        cols = data.get("collections", {}).get("items", []) if isinstance(data, dict) else []
        count = len(cols)
        return {
            "base_url": self.config.base_url,
            "collections_visible": count,
            "spaces_visible": count,
        }

    def close(self) -> None:
        session = getattr(self.client, "session", None)
        if session is not None:
            session.headers.pop("Authorization", None)
        if hasattr(self, "client") and hasattr(self.client, "close"):
            self.client.close()
        self.secret = ""
        self.config.access_token = SecretStr("")

    def list_containers(self) -> list[KnowledgeContainer]:
        containers: list[KnowledgeContainer] = []
        try:
            page = 1
            while True:
                res = self.client.get(f"/collections?page={page}&pageSize=50")
                data = res.json() if hasattr(res, "json") else {}
                coll_wrapper = data.get("collections", {}) if isinstance(data, dict) else {}
                items = coll_wrapper.get("items", []) if isinstance(coll_wrapper, dict) else []
                if not items:
                    break

                for coll in items:
                    coll_id = str(coll.get("id", ""))
                    coll_name = coll.get("name") or f"Coleção {coll_id}"
                    coll_desc = coll.get("description") or ""
                    container = KnowledgeContainer(
                        id=coll_id,
                        key=coll.get("slug") or coll_id,
                        name=coll_name,
                        container_type="collection",
                        source_type=self.SOURCE_TYPE,
                        is_accessible=True,
                        is_public=bool(coll.get("visibility") == "public"),
                        page_count=coll.get("articleCount") or 0,
                        description=coll_desc,
                        metadata={"siteId": coll.get("siteId")},
                    )
                    self._containers[coll_id] = container
                    containers.append(container)
                page += 1
                total_pages = coll_wrapper.get("pages", 1)
                if page > total_pages:
                    break

        except Exception as exc:
            self.log(f"Erro ao listar coleções Help Scout: {exc}")

        if not containers:
            container = KnowledgeContainer(
                id="col-1",
                key="docs",
                name="Docs",
                container_type="collection",
                source_type=self.SOURCE_TYPE,
                is_accessible=True,
                is_public=True,
                page_count=0,
                description="Coleção Geral",
            )
            self._containers["col-1"] = container
            containers.append(container)
        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []

        try:
            endpoint = (
                f"/collections/{container_id}/articles?page=1&pageSize=50"
                if container_id and container_id != "default"
                else "/articles?page=1&pageSize=50"
            )

            res = self.client.get(endpoint)
            data = res.json() if hasattr(res, "json") else {}
            art_wrapper = data.get("articles", {}) if isinstance(data, dict) else {}
            items = art_wrapper.get("items", []) if isinstance(art_wrapper, dict) else []

            for art in items:
                art_id = str(art.get("id", ""))
                title = art.get("name") or f"Artigo {art_id}"
                art_url = art.get("url") or f"https://docs.helpscout.net/article/{art_id}"
                updated_at = _datetime(art.get("updatedAt") or art.get("createdAt"))
                status = art.get("status", "published")

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
                    created_at=_datetime(art.get("createdAt")),
                    updated_at=updated_at,
                    document_type="article",
                    path=[title],
                    metadata={"slug": art.get("slug"), "views": art.get("views"), "status": status},
                )
                documents.append(meta)

        except Exception as exc:
            self.log(f"Erro ao listar artigos Help Scout: {exc}")

        return documents

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        res = self.client.get(f"/articles/{document_id}")
        data = res.json() if hasattr(res, "json") else {}
        art = data.get("article", {}) if isinstance(data, dict) and "article" in data else data
        if not art or not isinstance(art, dict):
            raise ResourceNotFoundError(f"Artigo Help Scout {document_id} não encontrado.")

        target_container = str(container_id or art.get("collectionId") or "col-1")
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
            raise TypeError("Documento bruto do Help Scout deve ser um objeto JSON.")

        doc_id = str(raw_document.get("id", ""))
        title = raw_document.get("name") or raw_document.get("title") or f"Artigo {doc_id}"
        html_content = raw_document.get("text") or raw_document.get("content") or ""
        updated_at = _datetime(raw_document.get("updatedAt") or raw_document.get("createdAt") or raw_document.get("updated_at"))
        created_at = _datetime(raw_document.get("createdAt"))
        art_url = raw_document.get("url") or f"https://docs.helpscout.net/article/{doc_id}"
        container_id = str(raw_document.get("_container_id") or raw_document.get("collectionId") or "col-1")

        soup = BeautifulSoup(html_content, "html.parser")
        markdown_body = markdownify(str(soup), heading_style="ATX", bullets="-").strip()
        markdown_body = normalize_markdown(markdown_body)

        container = self._containers.get(container_id)
        container_name = container.name if container else "Docs"

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
                "status": raw_document.get("status", "published"),
                "tags": raw_document.get("tags") or [],
            },
        )
