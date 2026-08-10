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


class NotionConnector(KnowledgeSourceConnector):
    SOURCE_TYPE = "notion_api"
    API_BASE_URL = "https://api.notion.com/v1"
    NOTION_VERSION = "2022-06-28"

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
        headers = (
            {
                "Authorization": f"Bearer {secret}",
                "Notion-Version": self.NOTION_VERSION,
            }
            if secret
            else {}
        )
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
            raise AuthenticationError("Informe o Integration Token do Notion.")
        payload = self.client.get_json("/users/me")
        if not isinstance(payload, dict):
            raise InvalidResponseError("A API do Notion retornou uma identidade inválida.")
        name = (
            payload.get("name")
            or (payload.get("bot") or {}).get("workspace_name")
            or "Notion Workspace"
        )
        return {"spaces_visible": 1, "identity": str(name)}

    def list_containers(self) -> list[KnowledgeContainer]:
        containers: list[KnowledgeContainer] = []
        payload = self.client.post_json(
            "/search", json_body={"filter": {"value": "database", "property": "object"}}
        )
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise InvalidResponseError("A API do Notion retornou uma lista de bancos inválida.")
        for item in payload["results"]:
            if not isinstance(item, dict):
                raise InvalidResponseError("A API do Notion retornou um banco inválido.")
            title_objs = item.get("title", [])
            if not isinstance(title_objs, list):
                raise InvalidResponseError("A API do Notion retornou um título inválido.")
            title = "".join(t.get("plain_text", "") for t in title_objs) or "Notion Database"
            db_id = str(item.get("id", ""))
            container = KnowledgeContainer(
                id=db_id,
                key=db_id,
                name=title,
                description="Notion Database",
            )
            containers.append(container)
            self._containers[db_id] = container

        if not containers:
            default_container = KnowledgeContainer(
                id=self.source.space_key or "notion_workspace",
                key=self.source.space_key or "notion_workspace",
                name=self.source.space_name or "Notion Workspace",
                description="Páginas do Notion",
            )
            containers.append(default_container)
            self._containers[default_container.id] = default_container

        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []
        payload = self.client.post_json(f"/databases/{container_id}/query", json_body={"page_size": 100})
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise InvalidResponseError("A API do Notion retornou uma lista de páginas inválida.")
        for page in payload["results"]:
            if not isinstance(page, dict):
                raise InvalidResponseError("A API do Notion retornou uma página inválida.")
            page_id = str(page.get("id", ""))
            props = page.get("properties", {})
            title = "Página Notion"
            for p in props.values():
                if p.get("type") == "title":
                    title = (
                        "".join(t.get("plain_text", "") for t in p.get("title", []))
                        or title
                    )
                    break
            updated_at = None
            if page.get("last_edited_time"):
                try:
                    updated_at = datetime.fromisoformat(
                        page["last_edited_time"].replace("Z", "+00:00")
                    )
                except (TypeError, ValueError) as exc:
                    raise InvalidResponseError("A API do Notion retornou uma data inválida.") from exc
            doc = KnowledgeDocumentMetadata(
                id=page_id,
                title=title,
                document_type="page",
                container_id=container_id,
                updated_at=updated_at,
                original_url=page.get("url", ""),
            )
            documents.append(doc)
        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        title = "Página Notion"
        content_lines: list[str] = []
        page_data = self.client.get_json(f"/pages/{document_id}")
        if not isinstance(page_data, dict):
            raise InvalidResponseError("A API do Notion retornou os metadados em formato inválido.")
        props = page_data.get("properties", {})
        for p in props.values():
            if p.get("type") == "title":
                title = "".join(t.get("plain_text", "") for t in p.get("title", [])) or title
                break

        blocks_payload = self.client.get_json(f"/blocks/{document_id}/children", params={"page_size": 100})
        if not isinstance(blocks_payload, dict) or not isinstance(blocks_payload.get("results"), list):
            raise InvalidResponseError("A API do Notion retornou os blocos em formato inválido.")
        for block in blocks_payload["results"]:
            if not isinstance(block, dict):
                raise InvalidResponseError("A API do Notion retornou um bloco inválido.")
            btype = block.get("type", "")
            bdata = block.get(btype, {})
            texts = bdata.get("rich_text", [])
            text_str = "".join(t.get("plain_text", "") for t in texts if isinstance(t, dict))
            if btype == "paragraph":
                content_lines.append(text_str)
            elif btype == "heading_1":
                content_lines.append(f"# {text_str}")
            elif btype == "heading_2":
                content_lines.append(f"## {text_str}")
            elif btype == "heading_3":
                content_lines.append(f"### {text_str}")
            elif btype == "bulleted_list_item":
                content_lines.append(f"- {text_str}")
            elif btype == "numbered_list_item":
                content_lines.append(f"1. {text_str}")
            elif btype == "to_do":
                checked = "x" if bdata.get("checked") else " "
                content_lines.append(f"- [{checked}] {text_str}")
            elif btype == "quote":
                content_lines.append(f"> {text_str}")
            elif btype == "code":
                lang = bdata.get("language", "")
                content_lines.append(f"```{lang}\n{text_str}\n```")
            elif text_str:
                content_lines.append(text_str)

        return KnowledgeDocument(
            id=document_id,
            title=title,
            content="\n\n".join(content_lines),
            document_type="page",
            container_id=container_id or self.source.space_key,
        )

    def close(self) -> None:
        if not self._injected_client and hasattr(self, "client"):
            self.client.close()
