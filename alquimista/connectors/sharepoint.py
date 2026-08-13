from __future__ import annotations

from datetime import datetime
from typing import Any

from ..errors import AuthenticationError, InvalidResponseError
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


class SharePointConnector(KnowledgeSourceConnector):
    SOURCE_TYPE = "sharepoint_graph"
    API_BASE_URL = "https://graph.microsoft.com/v1.0"

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
        self.source = source
        self.options = options
        self.markdown_options = markdown_options or MarkdownOptions()
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        self._injected_client = client is not None
        headers = {"Authorization": f"Bearer {secret}"} if secret else {}
        self.client = client or ApiHttpClient(
            self.API_BASE_URL,
            options,
            token=self.token,
            log=self.log,
            headers=headers,
        )
        self._containers: dict[str, KnowledgeContainer] = {}

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name,
            base_url=self.source.base_url or self.API_BASE_URL,
            space_key=self.source.space_key,
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_permissions=True,
            supports_updated_at=True,
            supports_bearer_token=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        if not self.secret:
            raise AuthenticationError("Informe o Token de Acesso do Microsoft Graph para o SharePoint.")
        payload = self.client.get_json("/sites/root")
        if not isinstance(payload, dict):
            raise InvalidResponseError("A API do SharePoint retornou um site raiz inválido.")
        name = payload.get("displayName") or "SharePoint Root Site"
        return {"spaces_visible": 1, "identity": str(name)}

    def list_containers(self) -> list[KnowledgeContainer]:
        containers: list[KnowledgeContainer] = []
        payload = self.client.get_json("/sites?search=*")
        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            raise InvalidResponseError("A API do SharePoint retornou uma lista de sites inválida.")
        seen_ids: set[str] = set()
        for item in payload["value"]:
            if not isinstance(item, dict):
                raise InvalidResponseError("A API do SharePoint retornou um site inválido.")
            site_id = str(item.get("id", ""))
            if not site_id or site_id in seen_ids:
                continue
            seen_ids.add(site_id)
            name = str(item.get("displayName") or item.get("name") or "SharePoint Site")
            container = KnowledgeContainer(
                id=site_id,
                key=site_id,
                name=name,
                description=item.get("description", "Site do SharePoint"),
                container_type="site",
                source_type=self.SOURCE_TYPE,
            )
            containers.append(container)
            self._containers[site_id] = container

        if not containers:
            default_id = self.source.space_key or "sharepoint_site"
            default_container = KnowledgeContainer(
                id=default_id,
                key=default_id,
                name=self.source.space_name or "SharePoint Site",
                description="Documentos do SharePoint",
                container_type="site",
                source_type=self.SOURCE_TYPE,
            )
            containers.append(default_container)
            self._containers[default_id] = default_container

        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []
        payload = self.client.get_json(f"/sites/{container_id}/drive/root/children")
        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            raise InvalidResponseError("A API do SharePoint retornou uma lista de documentos inválida.")
        for item in payload["value"]:
            if not isinstance(item, dict):
                raise InvalidResponseError("A API do SharePoint retornou um documento inválido.")
            item_id = str(item.get("id", ""))
            name = str(item.get("name", "Documento SharePoint"))
            updated_at = None
            if item.get("lastModifiedDateTime"):
                try:
                    updated_at = datetime.fromisoformat(item["lastModifiedDateTime"].replace("Z", "+00:00"))
                except (TypeError, ValueError) as exc:
                    raise InvalidResponseError("A API do SharePoint retornou uma data inválida.") from exc
            doc = KnowledgeDocumentMetadata(
                id=item_id,
                title=name,
                document_type="page" if not item.get("folder") else "folder",
                container_id=container_id,
                updated_at=updated_at,
                original_url=item.get("webUrl", ""),
            )
            documents.append(doc)
        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        title = "Documento SharePoint"
        item_data = self.client.get_json(f"/drive/items/{document_id}")
        if not isinstance(item_data, dict):
            raise InvalidResponseError("A API do SharePoint retornou os metadados em formato inválido.")
        title = str(item_data.get("name") or title)
        content_bytes = b""
        try:
            content_bytes = self.client.download(f"/drive/items/{document_id}/content")
        except Exception:
            pass
        content = content_bytes.decode("utf-8", errors="replace") if content_bytes else f"# {title}\n\nDocumento do SharePoint."

        container = self._containers.get(container_id or self.source.space_key or "")
        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or self.source.space_key,
            title=title,
            content=content,
            document_type="page",
            original_url=str(item_data.get("webUrl") or ""),
            source_type=self.SOURCE_TYPE,
            container_name=container.name if container else "SharePoint",
            metadata={"webUrl": item_data.get("webUrl"), "lastModifiedDateTime": item_data.get("lastModifiedDateTime")},
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        try:
            payload = self.client.get_json(f"/drive/items/{document_id}/children")
            if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
                return []
            result: list[KnowledgeDocumentMetadata] = []
            for item in payload["value"]:
                if isinstance(item, dict) and item.get("id"):
                    result.append(
                        KnowledgeDocumentMetadata(
                            id=str(item["id"]),
                            title=str(item.get("name") or "Item"),
                            document_type="page" if not item.get("folder") else "folder",
                            container_id=self.source.space_key or "sharepoint_site",
                            original_url=str(item.get("webUrl") or ""),
                        )
                    )
            return result
        except Exception:
            return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if not isinstance(raw_document, dict):
            raise TypeError("Documento bruto do SharePoint deve ser um objeto JSON.")
        doc_id = str(raw_document.get("id") or "")
        container_id = str(raw_document.get("container_id") or raw_document.get("_container_id") or self.source.space_key or "sharepoint_site")
        title = str(raw_document.get("title") or raw_document.get("name") or "Documento SharePoint")
        content = str(raw_document.get("content") or raw_document.get("markdown") or f"# {title}\n\nDocumento do SharePoint.")
        return KnowledgeDocument(
            id=doc_id,
            container_id=container_id,
            title=title,
            content=content,
            original_url=str(raw_document.get("original_url") or raw_document.get("webUrl") or ""),
            source_type=self.SOURCE_TYPE,
            container_name=str(raw_document.get("container_name") or "SharePoint"),
            metadata=dict(raw_document.get("metadata") or {}),
        )

    def close(self) -> None:
        session = getattr(self.client, "session", None)
        if session is not None:
            session.headers.pop("Authorization", None)
        if hasattr(self, "client") and hasattr(self.client, "close"):
            self.client.close()
        self.secret = ""
