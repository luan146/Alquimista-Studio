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
    ) -> None:
        self.source = source
        self.options = options
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
        for item in payload["value"]:
            if not isinstance(item, dict):
                raise InvalidResponseError("A API do SharePoint retornou um site inválido.")
            site_id = str(item.get("id", ""))
            name = str(item.get("displayName") or item.get("name") or "SharePoint Site")
            container = KnowledgeContainer(
                id=site_id,
                key=site_id,
                name=name,
                description=item.get("description", "Site do SharePoint"),
            )
            containers.append(container)
            self._containers[site_id] = container

        if not containers:
            default_container = KnowledgeContainer(
                id=self.source.space_key or "sharepoint_site",
                key=self.source.space_key or "sharepoint_site",
                name=self.source.space_name or "SharePoint Site",
                description="Documentos do SharePoint",
            )
            containers.append(default_container)
            self._containers[default_container.id] = default_container

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
        content = ""
        item_data = self.client.get_json(f"/drive/items/{document_id}")
        if not isinstance(item_data, dict):
            raise InvalidResponseError("A API do SharePoint retornou os metadados em formato inválido.")
        title = item_data.get("name", title)
        content_bytes = self.client.download(f"/drive/items/{document_id}/content")
        content = content_bytes.decode("utf-8", errors="replace")

        return KnowledgeDocument(
            id=document_id,
            title=title,
            content=content or f"# {title}\n\nDocumento do SharePoint",
            document_type="page",
            container_id=container_id or self.source.space_key,
        )

    def close(self) -> None:
        if not self._injected_client and hasattr(self, "client"):
            self.client.close()
