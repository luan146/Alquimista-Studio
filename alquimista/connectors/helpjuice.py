from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

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


class HelpjuiceConnector(KnowledgeSourceConnector):
    """Connector for Helpjuice Knowledge Base API."""

    SOURCE_TYPE = "helpjuice_api"

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
            base_url = "https://help.helpjuice.com"
        if not base_url.endswith("/api/v3"):
            api_url = f"{base_url}/api/v3"
        else:
            api_url = base_url

        self.source = source
        self.options = options
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        self.api_url = api_url

        headers: dict[str, str] = {"Accept": "application/json"}
        if secret.strip():
            headers["Authorization"] = f"Bearer {secret}"

        self.client = client or ApiHttpClient(
            self.api_url,
            options,
            token=self.token,
            log=self.log,
            headers=headers,
        )
        self._categories: dict[str, KnowledgeContainer] = {}

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or "Helpjuice",
            base_url=self.api_url,
            connector_version="v3",
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
        data = self.client.get_json("categories", params={"limit": 1})
        categories = (
            data.get("categories")
            or data.get("data")
            or (data if isinstance(data, list) else [])
        ) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        return {
            "categories_visible": len(categories),
            "auth": "API Key / Bearer Token" if self.secret else "Public",
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        data = self.client.get_json("categories")
        items = (
            data.get("categories")
            or data.get("data")
            or (data if isinstance(data, list) else [])
        ) if isinstance(data, dict) else (data if isinstance(data, list) else [])
        containers: list[KnowledgeContainer] = []
        for cat in items:
            cid = str(cat.get("id"))
            name = str(cat.get("name") or cid)
            c = KnowledgeContainer(
                id=cid,
                key=cid,
                name=name,
                description=str(cat.get("description") or ""),
                container_type="category",
                source_type=self.SOURCE_TYPE,
                updated_at=_datetime(cat.get("updated_at")),
            )
            self._categories[cid] = c
            containers.append(c)
        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []
        try:
            data = self.client.get_json(f"categories/{quote(container_id, safe='')}/questions")
            questions = (
                data.get("questions")
                or data.get("articles")
                or (data if isinstance(data, list) else [])
            ) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            cat = self._categories.get(container_id)
            cat_name = cat.name if cat else container_id
            for q in questions:
                qid = str(q.get("id"))
                title = str(q.get("name") or q.get("title") or q.get("question") or f"Artigo #{qid}")
                documents.append(
                    KnowledgeDocumentMetadata(
                        id=qid,
                        container_id=container_id,
                        title=title,
                        original_url=str(q.get("url") or ""),
                        created_at=_datetime(q.get("created_at")),
                        updated_at=_datetime(q.get("updated_at")),
                        document_type="article",
                        path=[cat_name, title],
                        metadata=q,
                    )
                )
        except Exception as exc:
            self.log(f"Erro ao listar artigos da categoria {container_id} no Helpjuice: {exc}")
        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        data = self.client.get_json(f"questions/{quote(document_id, safe='')}")
        raw_q = data.get("question") if isinstance(data, dict) and "question" in data else data
        q: dict[str, Any] = raw_q if isinstance(raw_q, dict) else {}
        title = str(q.get("name") or q.get("title") or q.get("question") or f"Artigo #{document_id}")
        html = str(q.get("answer") or q.get("body") or q.get("content") or "")
        content = normalize_markdown(markdownify(html, heading_style="ATX", bullets="-"))

        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or "cat-1",
            title=title,
            content=content,
            original_url=str(q.get("url") or ""),
            source_type=self.SOURCE_TYPE,
            container_name=container_id or "Helpjuice",
            created_at=_datetime(q.get("created_at")),
            updated_at=_datetime(q.get("updated_at")),
            path=[container_id or "Helpjuice", title],
            metadata=q,
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if isinstance(raw_document, dict):
            return KnowledgeDocument.model_validate(raw_document)
        raise TypeError("Documento bruto do Helpjuice deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        self.secret = ""
        self.client.close()

