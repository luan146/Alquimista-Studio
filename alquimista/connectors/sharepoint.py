from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from datetime import datetime
from typing import Any
from urllib.parse import unquote

from ..document_processing import get_global_processor_registry
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
            metadata={"space_key": self.source.space_key},
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

    def _paged(self, path: str, params: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
        """Yield every item of a Graph collection, following ``@odata.nextLink``."""
        next_path: str | None = path
        while next_path:
            self.token.check()
            payload = self.client.get_json(next_path, params=params)
            if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
                raise InvalidResponseError("A API do SharePoint retornou uma lista inválida.")
            for item in payload["value"]:
                if not isinstance(item, dict):
                    raise InvalidResponseError("A API do SharePoint retornou um item inválido.")
                yield item
            next_path = payload.get("@odata.nextLink") or None
            params = None  # nextLink already carries the query

    def list_containers(self) -> list[KnowledgeContainer]:
        containers: list[KnowledgeContainer] = []
        seen_ids: set[str] = set()
        for item in self._paged("/sites?search=*"):
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
        """Every convertible file of the site's document library, including subfolders."""
        registry = get_global_processor_registry()
        drive = self._drive(container_id)
        documents: list[KnowledgeDocumentMetadata] = []
        folders: deque[tuple[str, list[str]]] = deque([(f"{drive}/root/children", [])])
        while folders:
            children_path, folder_path = folders.popleft()
            for item in self._paged(children_path, params=_ITEM_QUERY):
                item_id = str(item.get("id") or "")
                name = str(item.get("name") or "")
                if not item_id or not name:
                    continue
                if "folder" in item:
                    folders.append((f"{drive}/items/{item_id}/children", [*folder_path, name]))
                    continue
                mime_type = str((item.get("file") or {}).get("mimeType") or "")
                if registry.get_processor(file_path=name, mime_type=mime_type) is None:
                    continue
                documents.append(
                    KnowledgeDocumentMetadata(
                        id=item_id,
                        title=name,
                        container_id=container_id,
                        updated_at=_graph_datetime(item.get("lastModifiedDateTime")),
                        etag=item.get("cTag") or item.get("eTag"),
                        original_url=str(item.get("webUrl") or ""),
                        path=[*folder_path, name],
                        metadata={"size": item.get("size"), "mime_type": mime_type},
                    )
                )
        return documents

    def _drive(self, container_id: str | None) -> str:
        site_id = container_id or self.source.space_key
        return f"/sites/{site_id}/drive" if site_id else "/drive"

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        drive = self._drive(container_id)
        item_data = self.client.get_json(f"{drive}/items/{document_id}")
        if not isinstance(item_data, dict):
            raise InvalidResponseError("A API do SharePoint retornou os metadados em formato inválido.")
        title = str(item_data.get("name") or "Documento SharePoint")
        folder_path = _folder_path(item_data)
        content_bytes = self.client.download(f"{drive}/items/{document_id}/content")
        converted = get_global_processor_registry().process_bytes(
            content_bytes,
            filename=title,
            mime_type=str((item_data.get("file") or {}).get("mimeType") or ""),
        )

        container = self._containers.get(container_id or self.source.space_key or "")
        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or self.source.space_key,
            title=converted.title or title,
            content=converted.content,
            original_url=str(item_data.get("webUrl") or ""),
            source_type=self.SOURCE_TYPE,
            container_name=container.name if container else "SharePoint",
            updated_at=_graph_datetime(item_data.get("lastModifiedDateTime")),
            etag=item_data.get("cTag") or item_data.get("eTag"),
            path=[*folder_path, title],
            metadata={
                **converted.metadata,
                "webUrl": item_data.get("webUrl"),
                "lastModifiedDateTime": item_data.get("lastModifiedDateTime"),
            },
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        payload = self.client.get_json(f"{self._drive(None)}/items/{document_id}/children")
        if not isinstance(payload, dict) or not isinstance(payload.get("value"), list):
            raise InvalidResponseError("A API do SharePoint retornou uma lista de itens inválida.")
        return [
            KnowledgeDocumentMetadata(
                id=str(item["id"]),
                title=str(item.get("name") or "Item"),
                document_type="page" if not item.get("folder") else "folder",
                container_id=self.source.space_key or "sharepoint_site",
                original_url=str(item.get("webUrl") or ""),
            )
            for item in payload["value"]
            if isinstance(item, dict) and item.get("id")
        ]

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


_ITEM_QUERY = {
    "$select": "id,name,folder,file,webUrl,lastModifiedDateTime,size,cTag,eTag,parentReference",
    "$top": "200",
}


def _graph_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidResponseError("A API do SharePoint retornou uma data inválida.") from exc


def _folder_path(item: dict[str, Any]) -> list[str]:
    """Folder names from ``parentReference.path`` (``/drives/{id}/root:/A/B``)."""
    parent = str((item.get("parentReference") or {}).get("path") or "")
    _, _, relative = parent.partition("root:")
    return [unquote(part) for part in relative.split("/") if part]
