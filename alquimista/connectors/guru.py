from __future__ import annotations

import base64
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


class GuruConnector(KnowledgeSourceConnector):
    """Connector for Guru Knowledge Cards and Collections API."""

    SOURCE_TYPE = "guru_api"
    BASE_URL = "https://api.getguru.com/api/v1"

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

        self.client = client or ApiHttpClient(
            self.BASE_URL,
            options,
            token=self.token,
            log=self.log,
            headers=headers,
        )
        self._collections: dict[str, KnowledgeContainer] = {}

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or "Guru",
            base_url=self.BASE_URL,
            connector_version="v1",
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_bearer_token=True,
            supports_updated_at=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        data = self.client.get_json("collections")
        items = data if isinstance(data, list) else []
        return {
            "collections_count": len(items),
            "auth": "Basic Auth / User Token",
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        data = self.client.get_json("collections")
        items = data if isinstance(data, list) else []
        containers: list[KnowledgeContainer] = []
        for col in items:
            cid = str(col.get("id"))
            name = str(col.get("name") or cid)
            c = KnowledgeContainer(
                id=cid,
                key=cid,
                name=name,
                description=str(col.get("description") or ""),
                container_type="collection",
                source_type=self.SOURCE_TYPE,
                updated_at=_datetime(col.get("dateModified")),
            )
            self._collections[cid] = c
            containers.append(c)
        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []
        try:
            data = self.client.get_json("search/cards", params={"collectionId": container_id, "limit": 100})
            cards = data if isinstance(data, list) else (data.get("cards") or [])
            col = self._collections.get(container_id)
            col_name = col.name if col else container_id
            for card in cards:
                cid = str(card.get("id"))
                title = str(card.get("preferredPhrase") or card.get("title") or f"Card #{cid}")
                documents.append(
                    KnowledgeDocumentMetadata(
                        id=cid,
                        container_id=container_id,
                        title=title,
                        created_at=_datetime(card.get("dateCreated")),
                        updated_at=_datetime(card.get("dateModified")),
                        document_type="card",
                        path=[col_name, title],
                        metadata=card,
                    )
                )
        except Exception as exc:
            self.log(f"Erro ao listar cards no Guru: {exc}")
        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        data = self.client.get_json(f"cards/{quote(document_id, safe='')}")
        card = data if isinstance(data, dict) else {}
        title = str(card.get("preferredPhrase") or card.get("title") or f"Card #{document_id}")
        html = str(card.get("content") or "")
        content = normalize_markdown(markdownify(html, heading_style="ATX", bullets="-"))

        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or "guru_cards",
            title=title,
            content=content,
            source_type=self.SOURCE_TYPE,
            container_name=container_id or "Guru Cards",
            created_at=_datetime(card.get("dateCreated")),
            updated_at=_datetime(card.get("dateModified")),
            path=[container_id or "Guru Cards", title],
            metadata=card,
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if isinstance(raw_document, dict):
            return KnowledgeDocument.model_validate(raw_document)
        raise TypeError("Documento bruto do Guru deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        self.secret = ""
        self.client.close()

