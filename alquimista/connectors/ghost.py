from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote, urlsplit

from markdownify import markdownify

from ..errors import AuthenticationError
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


class GhostConnector(KnowledgeSourceConnector):
    """Connector for Ghost publications via the Ghost Content API."""

    SOURCE_TYPE = "ghost_api"

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
        if not secret.strip():
            raise AuthenticationError("Informe a Content API Key do Ghost.")

        base_url = source.base_url.rstrip("/")
        if not base_url:
            base_url = "https://demo.ghost.io"
        parsed = urlsplit(base_url)
        self.origin = f"{parsed.scheme}://{parsed.netloc}"

        self.source = source
        self.options = options
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)

        self.client = client or ApiHttpClient(
            self.origin,
            options,
            token=self.token,
            log=self.log,
            headers={"Accept": "application/json"},
        )
        self.api_key = secret

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or "Ghost",
            base_url=self.origin,
            connector_version="v5",
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_public_access=True,
            supports_updated_at=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        data = self.client.get_json("ghost/api/content/settings/", params={"key": self.api_key})
        settings = data.get("settings") or {}
        return {
            "title": settings.get("title", "Ghost Publication"),
            "description": settings.get("description", ""),
            "url": settings.get("url", self.origin),
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        return [
            KnowledgeContainer(
                id="posts",
                key="posts",
                name="Posts",
                description="Publicações e artigos do Ghost",
                container_type="posts",
                source_type=self.SOURCE_TYPE,
            ),
            KnowledgeContainer(
                id="pages",
                key="pages",
                name="Páginas",
                description="Páginas fixas do Ghost",
                container_type="pages",
                source_type=self.SOURCE_TYPE,
            ),
        ]

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []
        endpoint = f"ghost/api/content/{container_id}/"
        try:
            data = self.client.get_json(endpoint, params={"key": self.api_key, "limit": "all"})
            items = data.get(container_id) or []
            for item in items:
                pid = str(item.get("id"))
                title = str(item.get("title") or f"Documento #{pid}")
                documents.append(
                    KnowledgeDocumentMetadata(
                        id=pid,
                        container_id=container_id,
                        title=title,
                        original_url=str(item.get("url") or ""),
                        created_at=_datetime(item.get("created_at")),
                        updated_at=_datetime(item.get("updated_at")),
                        document_type=container_id[:-1] if container_id.endswith("s") else container_id,
                        path=[container_id, title],
                        metadata=item,
                    )
                )
        except Exception as exc:
            self.log(f"Erro ao listar {container_id} no Ghost: {exc}")

        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        endpoint_type = container_id or "posts"
        endpoint = f"ghost/api/content/{endpoint_type}/{quote(document_id, safe='')}/"
        data = self.client.get_json(endpoint, params={"key": self.api_key})
        items = data.get(endpoint_type) or []
        item = items[0] if items else {}

        title = str(item.get("title") or f"Documento #{document_id}")
        html = str(item.get("html") or "")
        content = normalize_markdown(markdownify(html, heading_style="ATX", bullets="-"))

        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or "posts",
            title=title,
            content=content,
            original_url=str(item.get("url") or ""),
            source_type=self.SOURCE_TYPE,
            container_name="Posts" if container_id == "posts" else "Páginas",
            created_at=_datetime(item.get("created_at")),
            updated_at=_datetime(item.get("updated_at")),
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
        raise TypeError("Documento bruto do Ghost deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        self.secret = ""
        self.client.close()

