from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

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


class ContentfulConnector(KnowledgeSourceConnector):
    """Connector for Contentful Headless CMS (Content Delivery API)."""

    SOURCE_TYPE = "contentful_api"
    BASE_URL = "https://cdn.contentful.com"

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
            raise AuthenticationError("Informe o Content Delivery API Access Token (CDA) do Contentful.")

        self.source = source
        self.options = options
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)

        self.space_id = str(source.space_key or source.connector_options.get("space_id") or "default_space")
        self.environment_id = str(source.connector_options.get("environment") or "master")

        self.client = client or ApiHttpClient(
            self.BASE_URL,
            options,
            token=self.token,
            log=self.log,
            headers={
                "Authorization": f"Bearer {secret}",
                "Accept": "application/json",
            },
        )
        self._content_types: dict[str, str] = {}

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or f"Contentful ({self.space_id})",
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
        data = self.client.get_json(f"spaces/{self.space_id}")
        return {
            "name": data.get("name", self.space_id),
            "space_id": self.space_id,
            "environment": self.environment_id,
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        containers: list[KnowledgeContainer] = []
        try:
            data = self.client.get_json(f"spaces/{self.space_id}/environments/{self.environment_id}/content_types")
            items = data.get("items") or []
            for ct in items:
                sys = ct.get("sys") or {}
                cid = str(sys.get("id"))
                name = str(ct.get("name") or cid)
                self._content_types[cid] = name
                containers.append(
                    KnowledgeContainer(
                        id=cid,
                        key=cid,
                        name=f"Tipo: {name}",
                        description=str(ct.get("description") or ""),
                        container_type="content_type",
                        source_type=self.SOURCE_TYPE,
                    )
                )
        except Exception as exc:
            self.log(f"Erro ao listar tipos de conteúdo no Contentful: {exc}")

        if not containers:
            containers.append(
                KnowledgeContainer(
                    id="entries",
                    key="entries",
                    name="Todas as Entradas",
                    container_type="entries",
                    source_type=self.SOURCE_TYPE,
                )
            )
        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []
        params: dict[str, Any] = {"limit": 100}
        if container_id != "entries":
            params["content_type"] = container_id

        try:
            data = self.client.get_json(
                f"spaces/{self.space_id}/environments/{self.environment_id}/entries",
                params=params,
            )
            items = data.get("items") or []
            for entry in items:
                sys = entry.get("sys") or {}
                eid = str(sys.get("id"))
                fields = entry.get("fields") or {}
                title = str(
                    fields.get("title")
                    or fields.get("name")
                    or fields.get("headline")
                    or fields.get("slug")
                    or f"Entrada #{eid}"
                )
                documents.append(
                    KnowledgeDocumentMetadata(
                        id=eid,
                        container_id=container_id,
                        title=title,
                        created_at=_datetime(sys.get("createdAt")),
                        updated_at=_datetime(sys.get("updatedAt")),
                        document_type="entry",
                        path=[container_id, title],
                        metadata=entry,
                    )
                )
        except Exception as exc:
            self.log(f"Erro ao listar entradas no Contentful: {exc}")

        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        data = self.client.get_json(
            f"spaces/{self.space_id}/environments/{self.environment_id}/entries/{quote(document_id, safe='')}"
        )
        entry = data if isinstance(data, dict) else {}
        sys = entry.get("sys") or {}
        fields = entry.get("fields") or {}

        title = str(
            fields.get("title")
            or fields.get("name")
            or fields.get("headline")
            or fields.get("slug")
            or f"Entrada #{document_id}"
        )

        lines: list[str] = [f"# {title}", ""]
        for key, value in fields.items():
            if key in {"title", "name", "headline"}:
                continue
            if isinstance(value, str):
                if "<" in value and ">" in value:
                    lines.extend([f"## {key.capitalize()}", "", markdownify(value, heading_style="ATX"), ""])
                else:
                    lines.extend([f"## {key.capitalize()}", "", value, ""])
            elif isinstance(value, (int, float, bool)):
                lines.append(f"**{key}:** {value}  ")
            elif isinstance(value, dict):
                # Rich text or json field
                lines.extend([f"## {key.capitalize()}", "", str(value), ""])

        content = normalize_markdown("\n".join(lines))
        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or "entries",
            title=title,
            content=content,
            source_type=self.SOURCE_TYPE,
            container_name=container_id or "Contentful",
            created_at=_datetime(sys.get("createdAt")),
            updated_at=_datetime(sys.get("updatedAt")),
            path=[container_id or "Contentful", title],
            metadata=entry,
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if isinstance(raw_document, dict):
            return KnowledgeDocument.model_validate(raw_document)
        raise TypeError("Documento bruto do Contentful deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        self.secret = ""
        self.client.close()

