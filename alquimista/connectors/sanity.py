from __future__ import annotations

from datetime import datetime
from typing import Any

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


class SanityConnector(KnowledgeSourceConnector):
    """Connector for Sanity.io Content Lake via GROQ Query API."""

    SOURCE_TYPE = "sanity_api"
    API_VERSION = "v2021-06-07"

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

        self.project_id = str(source.space_key or source.connector_options.get("project_id") or "sanity_project")
        self.dataset = str(source.space_name or source.connector_options.get("dataset") or "production")

        base_url = f"https://{self.project_id}.api.sanity.io"
        headers: dict[str, str] = {"Accept": "application/json"}
        if secret.strip():
            headers["Authorization"] = f"Bearer {secret}"

        self.client = client or ApiHttpClient(
            base_url,
            options,
            token=self.token,
            log=self.log,
            headers=headers,
        )

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or f"Sanity ({self.project_id})",
            base_url=f"https://{self.project_id}.api.sanity.io",
            connector_version=self.API_VERSION,
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_public_access=True,
            supports_bearer_token=True,
            supports_updated_at=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        query = '*[!(_type in ["sanity.imageAsset", "sanity.fileAsset"])][0..2]'
        data = self.client.get_json(
            f"{self.API_VERSION}/data/query/{self.dataset}",
            params={"query": query},
        )
        return {
            "project_id": self.project_id,
            "dataset": self.dataset,
            "connected": bool(data.get("result") is not None),
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        query = 'array::unique(*[!(_type in ["sanity.imageAsset", "sanity.fileAsset"])]._type)'
        containers: list[KnowledgeContainer] = []
        try:
            data = self.client.get_json(
                f"{self.API_VERSION}/data/query/{self.dataset}",
                params={"query": query},
            )
            types = data.get("result") or []
            for t in types:
                type_name = str(t)
                containers.append(
                    KnowledgeContainer(
                        id=type_name,
                        key=type_name,
                        name=f"Tipo: {type_name.capitalize()}",
                        container_type="schema_type",
                        source_type=self.SOURCE_TYPE,
                    )
                )
        except Exception as exc:
            self.log(f"Erro ao listar tipos no Sanity: {exc}")

        if not containers:
            containers.append(
                KnowledgeContainer(
                    id="all_documents",
                    key="all_documents",
                    name="Todos os Documentos",
                    container_type="all_documents",
                    source_type=self.SOURCE_TYPE,
                )
            )
        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []
        query = (
            f'*[_type == "{container_id}"][0..100]{{_id, _type, _createdAt, _updatedAt, title, name, slug}}'
            if container_id != "all_documents"
            else '*[!(_type in ["sanity.imageAsset", "sanity.fileAsset"])][0..100]{_id, _type, _createdAt, _updatedAt, title, name, slug}'
        )

        try:
            data = self.client.get_json(
                f"{self.API_VERSION}/data/query/{self.dataset}",
                params={"query": query},
            )
            results = data.get("result") or []
            for item in results:
                doc_id = str(item.get("_id"))
                slug_obj = item.get("slug")
                slug_val = slug_obj.get("current") if isinstance(slug_obj, dict) else str(slug_obj or "")
                title = str(item.get("title") or item.get("name") or slug_val or f"Documento #{doc_id}")
                documents.append(
                    KnowledgeDocumentMetadata(
                        id=doc_id,
                        container_id=container_id,
                        title=title,
                        created_at=_datetime(item.get("_createdAt")),
                        updated_at=_datetime(item.get("_updatedAt")),
                        document_type=item.get("_type", "document"),
                        path=[container_id, title],
                        metadata=item,
                    )
                )
        except Exception as exc:
            self.log(f"Erro ao listar documentos no Sanity: {exc}")

        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        query = f'*[_id == "{document_id}"][0]'
        data = self.client.get_json(
            f"{self.API_VERSION}/data/query/{self.dataset}",
            params={"query": query},
        )
        doc = data.get("result") or {}
        title = str(doc.get("title") or doc.get("name") or f"Documento #{document_id}")

        lines: list[str] = [f"# {title}", ""]
        for k, v in doc.items():
            if k.startswith("_") or k in {"title", "name"}:
                continue
            if isinstance(v, str):
                if "<" in v and ">" in v:
                    lines.extend([f"## {k.capitalize()}", "", markdownify(v, heading_style="ATX"), ""])
                else:
                    lines.extend([f"## {k.capitalize()}", "", v, ""])
            elif isinstance(v, (int, float, bool)):
                lines.append(f"**{k}:** {v}  ")
            elif isinstance(v, list):
                # Portable text blocks
                block_texts = []
                for b in v:
                    if isinstance(b, dict) and b.get("_type") == "block":
                        children = b.get("children") or []
                        block_text = "".join(str(c.get("text", "")) for c in children if isinstance(c, dict))
                        if block_text:
                            block_texts.append(block_text)
                if block_texts:
                    lines.extend([f"## {k.capitalize()}", "", "\n\n".join(block_texts), ""])

        content = normalize_markdown("\n".join(lines))
        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or str(doc.get("_type") or "documents"),
            title=title,
            content=content,
            source_type=self.SOURCE_TYPE,
            container_name=container_id or "Sanity",
            created_at=_datetime(doc.get("_createdAt")),
            updated_at=_datetime(doc.get("_updatedAt")),
            path=[container_id or "Sanity", title],
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
        raise TypeError("Documento bruto do Sanity deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        self.secret = ""
        self.client.close()

