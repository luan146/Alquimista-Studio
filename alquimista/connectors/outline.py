from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

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


class OutlineConfig(BaseModel):
    """Runtime configuration for Outline Knowledge Base REST API."""

    model_config = ConfigDict(validate_assignment=True)

    base_url: str
    access_token: SecretStr
    page_size: int = Field(default=100, ge=1, le=100)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            value = f"https://{value}"
        parsed = urlparse(value)
        if not parsed.hostname:
            raise ValueError("Informe uma URL válida para a instância do Outline.")
        if not value.endswith("/api"):
            value = f"{value}/api"
        return value


class OutlineConnector(KnowledgeSourceConnector):
    SOURCE_TYPE = "outline_api"
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
            raise ValueError("A configuração não pertence ao conector Outline.")
        if not secret.strip():
            raise AuthenticationError("Informe o API Key / Bearer Token do Outline.")

        self.source = source
        self.options = options
        self.markdown_options = markdown_options or MarkdownOptions()
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)

        self.config = OutlineConfig(
            base_url=source.base_url or "https://app.getoutline.com/api",
            access_token=SecretStr(secret),
        )

        auth_header = f"Bearer {secret}" if not secret.lower().startswith("bearer ") else secret
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
        origin = self.config.base_url.replace("/api", "")
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or "Outline Knowledge Base",
            base_url=origin,
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
        res = self.client.post("/collections.list", json={"limit": 1})
        data = res.json() if hasattr(res, "json") else {}
        collections = data.get("data", []) if isinstance(data, dict) else []
        count = len(collections)
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
            offset = 0
            limit = 100
            while True:
                res = self.client.post("/collections.list", json={"offset": offset, "limit": limit})
                data = res.json() if hasattr(res, "json") else {}
                items = data.get("data", []) if isinstance(data, dict) else []
                if not items:
                    break

                for coll in items:
                    coll_id = str(coll.get("id", ""))
                    coll_name = coll.get("name") or f"Coleção {coll_id}"
                    coll_desc = coll.get("description") or ""
                    container = KnowledgeContainer(
                        id=coll_id,
                        key=coll.get("urlId") or coll_id,
                        name=coll_name,
                        container_type="collection",
                        source_type=self.SOURCE_TYPE,
                        is_accessible=True,
                        is_public=not bool(coll.get("private")),
                        page_count=0,
                        description=coll_desc,
                        metadata={"color": coll.get("color"), "sharing": coll.get("sharing")},
                    )
                    self._containers[coll_id] = container
                    containers.append(container)
                offset += len(items)
                if len(items) < limit:
                    break

        except Exception as exc:
            self.log(f"Erro ao listar coleções Outline: {exc}")

        if not containers:
            container = KnowledgeContainer(
                id="col-1",
                key="col-1",
                name="Coleção Outline",
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
            offset = 0
            limit = 100
            payload: dict[str, Any] = {"offset": offset, "limit": limit}
            if container_id and container_id != "default":
                payload["collectionId"] = container_id

            res = self.client.post("/documents.list", json=payload)
            data = res.json() if hasattr(res, "json") else {}
            items = data.get("data", []) if isinstance(data, dict) else []

            origin = self.config.base_url.replace("/api", "")
            for doc in items:
                doc_id = str(doc.get("id", ""))
                title = doc.get("title") or f"Documento {doc_id}"
                url_path = doc.get("url") or f"/doc/{doc_id}"
                doc_url = urljoin(origin, url_path)
                updated_at = _datetime(doc.get("updatedAt") or doc.get("createdAt"))
                parent_id = str(doc.get("parentDocumentId") or "") if doc.get("parentDocumentId") else None

                raw = {
                    **doc,
                    "_container_id": container_id,
                    "_path": [title],
                }
                self._documents[(container_id, doc_id)] = raw

                meta = KnowledgeDocumentMetadata(
                    id=doc_id,
                    title=title,
                    container_id=container_id,
                    parent_id=parent_id,
                    original_url=doc_url,
                    created_at=_datetime(doc.get("createdAt")),
                    updated_at=updated_at,
                    document_type="document",
                    path=[title],
                    metadata={"emoji": doc.get("emoji"), "revision": doc.get("revision")},
                )
                documents.append(meta)

        except Exception as exc:
            self.log(f"Erro ao listar documentos Outline: {exc}")

        return documents

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        res = self.client.post("/documents.info", json={"id": document_id})
        data = res.json() if hasattr(res, "json") else {}
        doc = data.get("data", {}) if isinstance(data, dict) and "data" in data else data
        if not doc:
            raise ResourceNotFoundError(f"Documento Outline {document_id} não encontrado.")

        target_container = str(container_id or doc.get("collectionId") or "col-1")
        base_meta = self._documents.get((target_container, str(document_id)), {})
        merged = {
            **base_meta,
            **doc,
            "_container_id": target_container,
        }
        return self.normalize_document(merged)

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if not isinstance(raw_document, dict):
            raise TypeError("Documento bruto do Outline deve ser um objeto JSON.")

        doc_id = str(raw_document.get("id", ""))
        title = raw_document.get("title") or f"Documento {doc_id}"
        text_content = raw_document.get("text") or raw_document.get("markdown") or ""
        markdown_body = normalize_markdown(text_content)
        origin = self.config.base_url.replace("/api", "")
        url_path = raw_document.get("url") or f"/doc/{doc_id}"
        doc_url = urljoin(origin, url_path)
        updated_at = _datetime(raw_document.get("updatedAt") or raw_document.get("createdAt") or raw_document.get("updated_at"))
        created_at = _datetime(raw_document.get("createdAt"))
        container_id = str(raw_document.get("_container_id") or raw_document.get("collectionId") or "col-1")
        parent_id = str(raw_document.get("parentDocumentId") or "") if raw_document.get("parentDocumentId") else None

        container = self._containers.get(container_id)
        container_name = container.name if container else "Coleção Outline"

        return KnowledgeDocument(
            id=doc_id,
            container_id=container_id,
            parent_id=parent_id,
            title=title,
            content=markdown_body,
            original_url=doc_url,
            created_at=created_at,
            updated_at=updated_at,
            source_type=self.SOURCE_TYPE,
            container_name=container_name,
            path=raw_document.get("_path") or [title],
            metadata={
                "emoji": raw_document.get("emoji"),
                "revision": raw_document.get("revision"),
            },
        )
