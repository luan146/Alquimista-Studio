from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote, urlsplit

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


class StrapiConnector(KnowledgeSourceConnector):
    """Connector for Strapi Headless CMS (v4 / v5 REST API)."""

    SOURCE_TYPE = "strapi_api"

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
            base_url = "https://strapi.example.com"
        parsed = urlsplit(base_url)
        self.origin = f"{parsed.scheme}://{parsed.netloc}"

        self.source = source
        self.options = options
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)

        headers: dict[str, str] = {"Accept": "application/json"}
        if secret.strip():
            headers["Authorization"] = f"Bearer {secret}"

        self.client = client or ApiHttpClient(
            self.origin,
            options,
            token=self.token,
            log=self.log,
            headers=headers,
        )
        self.collection_name = str(source.space_key or source.connector_options.get("collection") or "articles")

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or f"Strapi ({self.collection_name})",
            base_url=self.origin,
            connector_version="v4/v5",
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_bearer_token=True,
            supports_public_access=True,
            supports_updated_at=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        data = self.client.get_json(f"api/{self.collection_name}", params={"pagination[limit]": 1})
        return {
            "collection": self.collection_name,
            "connected": True,
            "meta": data.get("meta") or {},
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        return [
            KnowledgeContainer(
                id=self.collection_name,
                key=self.collection_name,
                name=f"Coleção: {self.collection_name.capitalize()}",
                description=f"Entradas da coleção {self.collection_name} no Strapi",
                container_type="collection",
                source_type=self.SOURCE_TYPE,
            )
        ]

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []
        try:
            data = self.client.get_json(f"api/{container_id}", params={"pagination[pageSize]": 100})
            items = data.get("data") or []
            for item in items:
                eid = str(item.get("id"))
                attrs = item.get("attributes") or item
                title = str(attrs.get("title") or attrs.get("name") or attrs.get("slug") or f"Documento #{eid}")
                documents.append(
                    KnowledgeDocumentMetadata(
                        id=eid,
                        container_id=container_id,
                        title=title,
                        created_at=_datetime(attrs.get("createdAt")),
                        updated_at=_datetime(attrs.get("updatedAt")),
                        document_type="entry",
                        path=[container_id, title],
                        metadata=attrs,
                    )
                )
        except Exception as exc:
            self.log(f"Erro ao listar documentos no Strapi: {exc}")

        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        col = container_id or self.collection_name
        data = self.client.get_json(f"api/{col}/{quote(document_id, safe='')}")
        item = data.get("data") or data if isinstance(data, dict) else {}
        attrs = item.get("attributes") or item

        title = str(attrs.get("title") or attrs.get("name") or attrs.get("slug") or f"Documento #{document_id}")
        raw_body = attrs.get("content") or attrs.get("body") or attrs.get("description") or ""

        # Format if HTML or plain Markdown
        if isinstance(raw_body, str) and "<" in raw_body and ">" in raw_body:
            content = normalize_markdown(markdownify(raw_body, heading_style="ATX", bullets="-"))
        else:
            content = normalize_markdown(str(raw_body))

        return KnowledgeDocument(
            id=document_id,
            container_id=col,
            title=title,
            content=content,
            source_type=self.SOURCE_TYPE,
            container_name=col.capitalize(),
            created_at=_datetime(attrs.get("createdAt")),
            updated_at=_datetime(attrs.get("updatedAt")),
            path=[col, title],
            metadata=attrs,
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if isinstance(raw_document, dict):
            return KnowledgeDocument.model_validate(raw_document)
        raise TypeError("Documento bruto do Strapi deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        self.secret = ""
        self.client.close()

