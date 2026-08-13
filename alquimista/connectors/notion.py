from __future__ import annotations

from datetime import datetime
from typing import Any

from ..browser.contracts import (
    CancellationLike,
    DiscoveryPage,
    DocumentMetadata,
    SearchResult,
)
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
from .notion_parser import NotionDocumentParser


class NotionConnector(KnowledgeSourceConnector):
    SOURCE_TYPE = "notion_api"
    API_BASE_URL = "https://api.notion.com/v1"
    NOTION_VERSION = "2026-03-11"

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
        headers = {"Notion-Version": self.NOTION_VERSION}
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        self.client = client or ApiHttpClient(
            self.API_BASE_URL,
            options,
            token=self.token,
            log=self.log,
            headers=headers,
        )
        self._containers: dict[str, KnowledgeContainer] = {}
        self.parser = NotionDocumentParser()

    def _page(self, path: str, *, method: str = "GET", cursor: str | None = None) -> dict[str, Any]:
        self.token.check()
        if method == "POST":
            body: dict[str, Any] = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor
            payload = self.client.post_json(path, json_body=body)
        else:
            params: dict[str, Any] = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            payload = self.client.get_json(path, params=params)
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise InvalidResponseError("A API do Notion retornou uma página inválida.")
        return payload

    def _paginate(self, path: str, *, method: str = "GET") -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        cursor: str | None = None
        seen: set[str] = set()
        while True:
            payload = self._page(path, method=method, cursor=cursor)
            result.extend(item for item in payload["results"] if isinstance(item, dict))
            if not payload.get("has_more"):
                return result
            next_cursor = payload.get("next_cursor")
            if not isinstance(next_cursor, str) or next_cursor in seen:
                raise InvalidResponseError("Cursor de paginação do Notion inválido ou repetido.")
            seen.add(next_cursor)
            cursor = next_cursor

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name,
            base_url=self.source.base_url or self.API_BASE_URL,
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
        workspace_id = self.source.space_key or "notion_workspace"
        workspace = KnowledgeContainer(id=workspace_id, key=workspace_id, name=self.source.space_name or "Notion Workspace", description="Páginas do Notion", container_type="workspace", source_type=self.SOURCE_TYPE)
        containers = [workspace]
        self._containers[workspace.id] = workspace
        for item in self._paginate("/search", method="POST"):
            if item.get("object") not in {"data_source", "database"}:
                continue
            title_objs = item.get("title", [])
            if not isinstance(title_objs, list):
                title_objs = []
            title = "".join(t.get("plain_text", "") for t in title_objs) or "Notion Database"
            db_id = str(item.get("id", ""))
            container = KnowledgeContainer(
                id=db_id,
                key=db_id,
                name=title,
                description="Notion Database",
                container_type="data_source",
                source_type=self.SOURCE_TYPE,
            )
            if db_id and db_id not in self._containers:
                containers.append(container)
            self._containers[db_id] = container
        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        path = "/search" if container_id == (self.source.space_key or "notion_workspace") else f"/data_sources/{container_id}/query"
        pages = self._paginate(path, method="POST")
        if path == "/search":
            pages = [page for page in pages if page.get("object") == "page"]
        documents: list[KnowledgeDocumentMetadata] = []
        for page in pages:
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

    def list_root_documents(self, container_id: str, *, cursor: str | None = None, limit: int = 100, etag: str | None = None, token: CancellationLike | None = None) -> DiscoveryPage[DocumentMetadata]:
        del etag
        if token: token.check()
        path = "/search" if container_id == (self.source.space_key or "notion_workspace") else f"/data_sources/{container_id}/query"
        payload = self._page(path, method="POST", cursor=cursor)
        items = tuple(DocumentMetadata(source_id=self.source.id, **doc.model_dump()) for doc in self._metadata_items(payload["results"], container_id))
        return DiscoveryPage(items=items, cursor=cursor, next_cursor=payload.get("next_cursor") if payload.get("has_more") else None)

    def list_document_children(self, container_id: str, parent_id: str, *, cursor: str | None = None, limit: int = 100, etag: str | None = None, token: CancellationLike | None = None) -> DiscoveryPage[DocumentMetadata]:
        del etag, limit
        if token: token.check()
        payload = self._page(f"/blocks/{parent_id}/children", cursor=cursor)
        items = tuple(DocumentMetadata(source_id=self.source.id, **doc.model_dump()) for doc in self._metadata_items(payload["results"], container_id))
        return DiscoveryPage(items=items, cursor=cursor, next_cursor=payload.get("next_cursor") if payload.get("has_more") else None)

    def search_documents(self, container_id: str | None, query: str, *, cursor: str | None = None, limit: int = 100, etag: str | None = None, token: CancellationLike | None = None) -> DiscoveryPage[SearchResult]:
        del limit, etag
        if token: token.check()
        body = {"query": query, "page_size": 100}
        if cursor: body["start_cursor"] = cursor
        payload = self.client.post_json("/search", json_body=body)
        if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
            raise InvalidResponseError("A API do Notion retornou uma busca inválida.")
        docs = self._metadata_items(payload["results"], container_id or self.source.space_key or "notion_workspace")
        return DiscoveryPage(items=tuple(SearchResult(document=DocumentMetadata(source_id=self.source.id, **doc.model_dump())) for doc in docs), cursor=cursor, next_cursor=payload.get("next_cursor") if payload.get("has_more") else None)

    def _metadata_items(self, pages: list[Any], container_id: str) -> list[KnowledgeDocumentMetadata]:
        result: list[KnowledgeDocumentMetadata] = []
        for page in pages:
            if not isinstance(page, dict): continue
            props = page.get("properties", {}) or {}
            title = "Página Notion"
            for prop in props.values():
                if isinstance(prop, dict) and prop.get("type") == "title":
                    title = self.parser._text(prop.get("title")) or title
            result.append(KnowledgeDocumentMetadata(id=str(page.get("id") or ""), title=title, document_type="page", container_id=container_id, original_url=str(page.get("url") or "")))
        return result

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        title = "Página Notion"
        page_data = self.client.get_json(f"/pages/{document_id}")
        if not isinstance(page_data, dict):
            raise InvalidResponseError("A API do Notion retornou os metadados em formato inválido.")
        props = page_data.get("properties", {})
        for p in props.values():
            if p.get("type") == "title":
                title = "".join(t.get("plain_text", "") for t in p.get("title", [])) or title
                break

        blocks = self._paginate(f"/blocks/{document_id}/children")
        count = 0
        stack = list(reversed(blocks))
        while stack:
            block = stack.pop()
            count += 1
            if count > self.parser.max_blocks: raise InvalidResponseError("O documento Notion excedeu 10.000 blocos.")
            if block.get("has_children"):
                children = self._paginate(f"/blocks/{block.get('id')}/children")
                block["_children"] = children
            stack.extend(reversed(block.get("_children", [])))
        content = self.parser.render(blocks)

        return KnowledgeDocument(
            id=document_id,
            title=title,
            content=content,
            document_type="page",
            container_id=container_id or self.source.space_key,
            original_url=str(page_data.get("url") or ""),
            source_type=self.SOURCE_TYPE,
            container_name=self._containers.get(container_id or self.source.space_key, KnowledgeContainer(id=container_id or self.source.space_key or "notion_workspace", key=container_id or self.source.space_key or "notion_workspace", name="Notion Workspace", container_type="workspace", source_type=self.SOURCE_TYPE)).name,
            metadata={"last_edited_time": page_data.get("last_edited_time")},
        )

    def close(self) -> None:
        if not self._injected_client and hasattr(self, "client"):
            self.client.close()
