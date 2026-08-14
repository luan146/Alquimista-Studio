from __future__ import annotations

import base64
from datetime import datetime
from typing import Any
from urllib.parse import quote

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


class ReadMeConnector(KnowledgeSourceConnector):
    """Connector for ReadMe Documentation API."""

    SOURCE_TYPE = "readme_api"
    BASE_URL = "https://dash.readme.com/api/v1"

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
            raise AuthenticationError("Informe a API Key do ReadMe.")
        self.source = source
        self.options = options
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)

        encoded_auth = base64.b64encode(f"{secret}:".encode("utf-8")).decode("utf-8")
        self.client = client or ApiHttpClient(
            self.BASE_URL,
            options,
            token=self.token,
            log=self.log,
            headers={
                "Authorization": f"Basic {encoded_auth}",
                "Accept": "application/json",
            },
        )
        self._categories: dict[str, KnowledgeContainer] = {}

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or "ReadMe",
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
        data = self.client.get_json("version")
        versions = data if isinstance(data, list) else []
        return {
            "versions_count": len(versions),
            "auth": "ReadMe API Key",
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        data = self.client.get_json("categories")
        categories = data if isinstance(data, list) else []
        containers: list[KnowledgeContainer] = []
        for cat in categories:
            cid = str(cat.get("slug") or cat.get("_id") or "")
            name = str(cat.get("title") or cid)
            c = KnowledgeContainer(
                id=cid,
                key=cid,
                name=name,
                container_type="category",
                source_type=self.SOURCE_TYPE,
                updated_at=_datetime(cat.get("updatedAt")),
            )
            self._categories[cid] = c
            containers.append(c)
        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []
        try:
            data = self.client.get_json(f"categories/{quote(container_id, safe='')}/docs")
            docs = data if isinstance(data, list) else []
            cat = self._categories.get(container_id)
            cat_name = cat.name if cat else container_id
            for doc in docs:
                slug = str(doc.get("slug") or doc.get("_id") or "")
                title = str(doc.get("title") or slug)
                documents.append(
                    KnowledgeDocumentMetadata(
                        id=slug,
                        container_id=container_id,
                        title=title,
                        created_at=_datetime(doc.get("createdAt")),
                        updated_at=_datetime(doc.get("updatedAt")),
                        document_type="doc",
                        path=[cat_name, title],
                        metadata=doc,
                    )
                )
        except Exception as exc:
            self.log(f"Erro ao listar docs na categoria {container_id} do ReadMe: {exc}")
        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        data = self.client.get_json(f"docs/{quote(document_id, safe='')}")
        doc = data if isinstance(data, dict) else {}
        title = str(doc.get("title") or document_id)
        body = str(doc.get("body") or doc.get("body_html") or "")
        content = normalize_markdown(body)

        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or "readme_docs",
            title=title,
            content=content,
            source_type=self.SOURCE_TYPE,
            container_name=container_id or "ReadMe Docs",
            created_at=_datetime(doc.get("createdAt")),
            updated_at=_datetime(doc.get("updatedAt")),
            path=[container_id or "ReadMe", title],
            metadata=doc,
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if isinstance(raw_document, dict):
            return KnowledgeDocument.model_validate(raw_document)
        raise TypeError("Documento bruto do ReadMe deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        self.secret = ""
        self.client.close()

