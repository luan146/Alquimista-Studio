from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ..errors import AuthenticationError, InvalidResponseError, ResourceNotFoundError
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


class GitBookConfig(BaseModel):
    """Non-persistent runtime configuration for the GitBook API."""

    model_config = ConfigDict(validate_assignment=True)

    organization_id: str
    access_token: SecretStr
    api_base_url: str = "https://api.gitbook.com/v1"
    page_limit: int = Field(default=1000, ge=1, le=1000)

    @field_validator("organization_id")
    @classmethod
    def validate_organization_id(cls, value: str) -> str:
        value = value.strip()
        if not value or any(char in value for char in "/?#"):
            raise ValueError("Informe um ID de organização GitBook válido.")
        return value


def _datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


class GitBookConnector(KnowledgeSourceConnector):
    SOURCE_TYPE = "gitbook_api"
    API_VERSION = "v1"
    API_BASE_URL = "https://api.gitbook.com/v1"

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
            raise ValueError("A configuração não pertence ao conector GitBook.")
        if not secret.strip():
            raise AuthenticationError("Informe o Personal Access Token do GitBook.")
        self.source = source
        self.options = options
        self.markdown_options = markdown_options or MarkdownOptions()
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        connector_options = source.connector_options
        self.config = GitBookConfig(
            organization_id=str(connector_options.get("organization_id") or source.space_key),
            access_token=SecretStr(secret),
            api_base_url=str(connector_options.get("api_base_url") or source.base_url or self.API_BASE_URL),
            page_limit=int(connector_options.get("page_limit", 1000)),
        )
        self._injected_client = client is not None
        self.client = client or ApiHttpClient(
            self.config.api_base_url,
            options,
            token=self.token,
            log=self.log,
            headers={"Authorization": f"Bearer {secret}"},
        )
        self._containers: dict[str, KnowledgeContainer] = {}
        self._documents: dict[tuple[str, str], dict[str, Any]] = {}

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name,
            base_url=self.config.api_base_url,
            connector_version=self.API_VERSION,
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_attachments=False,
            supports_permissions=True,
            supports_search=False,
            supports_updated_at=True,
            supports_bearer_token=True,
            supports_public_access=False,
            supports_document_download=False,
        )

    def validate_connection(self) -> dict[str, Any]:
        organization = self.client.get_json(f"/orgs/{quote(self.config.organization_id, safe='_-')}")
        if not isinstance(organization, dict):
            raise InvalidResponseError("A API do GitBook não retornou uma organização válida.")
        return {
            "organization_id": str(organization.get("id") or self.config.organization_id),
            "organization_name": str(organization.get("title") or organization.get("name") or self.config.organization_id),
            "spaces_visible": "não consultado",
        }

    def _paged_spaces(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        page: str | None = None
        seen: set[str] = set()
        while len(items) < self.config.page_limit:
            params: dict[str, Any] = {"limit": min(1000, self.config.page_limit - len(items))}
            if page:
                if page in seen:
                    raise InvalidResponseError("A API do GitBook repetiu o cursor de espaços.")
                seen.add(page)
                params["page"] = page
            data = self.client.get_json(
                f"/orgs/{quote(self.config.organization_id, safe='_-')}/spaces",
                params=params,
            )
            if not isinstance(data, dict):
                raise InvalidResponseError("A API do GitBook retornou uma lista de espaços inválida.")
            batch = data.get("items") or []
            if not isinstance(batch, list):
                raise InvalidResponseError("A API do GitBook retornou itens de espaços inválidos.")
            items.extend(item for item in batch if isinstance(item, dict) and item.get("id"))
            next_page = str((data.get("next") or {}).get("page") or "") or None
            if not batch or not next_page:
                break
            page = next_page
        return items[: self.config.page_limit]

    def list_containers(self) -> list[KnowledgeContainer]:
        containers: list[KnowledgeContainer] = []
        for item in self._paged_spaces():
            if item.get("deletedAt"):
                continue
            identifier = str(item["id"])
            urls = item.get("urls") or {}
            container = KnowledgeContainer(
                id=identifier,
                key=identifier,
                name=str(item.get("title") or identifier),
                description=str(item.get("description") or "") or None,
                container_type="space",
                source_type=self.SOURCE_TYPE,
                updated_at=_datetime(item.get("updatedAt")),
                metadata={
                    "visibility": item.get("visibility"),
                    "language": item.get("language"),
                    "organization_id": self.config.organization_id,
                    "original_url": urls.get("public") or urls.get("published") or urls.get("location") or urls.get("app"),
                },
            )
            self._containers[identifier] = container
            containers.append(container)
        return containers

    def _flatten_pages(
        self,
        pages: list[Any],
        *,
        container_id: str,
        parent_id: str | None = None,
        parent_path: list[str] | None = None,
        parent_ancestors: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        # Iterative pre-order DFS to avoid RecursionError on deeply nested
        # GitBook hierarchies. Each stack entry is a single page plus the
        # parent context it inherits. Top-level pages are pushed in reverse so
        # they pop in forward order; children are likewise pushed in reverse on
        # top of the stack, which yields true pre-order (parent, then its
        # children subtree, then next sibling) matching the recursive version.
        stack: list[tuple[Any, str | None, list[str] | None, list[dict[str, str]] | None]] = [
            (raw, parent_id, parent_path, parent_ancestors) for raw in reversed(pages)
        ]
        while stack:
            raw, current_parent_id, current_parent_path, current_parent_ancestors = stack.pop()
            if not isinstance(raw, dict) or not raw.get("id"):
                continue
            item = dict(raw)
            item["_container_id"] = container_id
            resolved_parent = raw.get("parent") or current_parent_id
            item["_parent_id"] = str(resolved_parent) if resolved_parent else None
            title = str(raw.get("title") or raw.get("id"))
            item["_path"] = [*(current_parent_path or []), title]
            item["_ancestors"] = list(current_parent_ancestors or [])
            result.append(item)
            children = raw.get("pages")
            if isinstance(children, list):
                child_ancestors = [
                    *(current_parent_ancestors or []),
                    {"id": str(raw["id"]), "title": title},
                ]
                for child in reversed(children):
                    stack.append(
                        (child, str(raw["id"]), item["_path"], child_ancestors)
                    )
        return result

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        data = self.client.get_json(
            f"/spaces/{quote(str(container_id), safe='_-')}/content/pages",
            params={"metadata": "true", "computed": "false"},
        )
        if isinstance(data, dict):
            raw_pages = data.get("pages") or data.get("items") or []
        else:
            raw_pages = data
        if not isinstance(raw_pages, list):
            raise InvalidResponseError("A API do GitBook retornou páginas inválidas.")
        flattened = self._flatten_pages(raw_pages, container_id=container_id)
        result: list[KnowledgeDocumentMetadata] = []
        for page in flattened:
            metadata = self._metadata(page, container_id)
            self._documents[(container_id, metadata.id)] = page
            result.append(metadata)
        return result

    def get_document(
        self, document_id: str, container_id: str | None = None
    ) -> KnowledgeDocument:
        locations = (
            [(str(container_id), str(document_id))]
            if container_id and (str(container_id), str(document_id)) in self._documents
            else [key for key in self._documents if key[1] == str(document_id)]
        )
        if not locations:
            target_container = container_id or self.source.space_key
            if not target_container:
                raise ResourceNotFoundError("A página GitBook não foi descoberta nesta sessão e o container_id não foi informado.")
            locations = [(str(target_container), str(document_id))]
        container_id = locations[0][0]
        data = self.client.get_json(
            f"/spaces/{quote(container_id, safe='_-')}/content/page/{quote(str(document_id), safe='_-')}",
            params={"format": "markdown", "computed": "false", "metadata": "false"},
        )
        if not isinstance(data, dict):
            raise InvalidResponseError("A API do GitBook retornou um documento inválido.")
        base_meta = self._documents.get((container_id, str(document_id)), {})
        raw = {
            **base_meta,
            **data,
            "_container_id": container_id,
            "_etag": getattr(self.client, "last_response_headers", {}).get("etag"),
        }
        return self.normalize_document(raw)

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        children: list[KnowledgeDocumentMetadata] = []
        for raw in self._documents.values():
            if str(raw.get("_parent_id") or "") == str(document_id):
                children.append(self._metadata(raw, str(raw["_container_id"])))
        return children

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if not isinstance(raw_document, dict):
            raise TypeError("Documento bruto do GitBook deve ser um objeto JSON.")
        container_id = str(raw_document.get("_container_id") or "")
        metadata = self._metadata(raw_document, container_id)
        urls = raw_document.get("urls") or {}
        content = str(raw_document.get("markdown") or "").strip()
        container = self._containers.get(container_id)
        return KnowledgeDocument(
            id=metadata.id,
            container_id=container_id,
            parent_id=metadata.parent_id,
            title=metadata.title,
            content=content,
            original_url=str(urls.get("public") or urls.get("published") or urls.get("app") or ""),
            created_at=metadata.created_at,
            updated_at=metadata.updated_at,
            etag=metadata.etag,
            source_type=self.SOURCE_TYPE,
            container_name=container.name if container else container_id,
            path=metadata.path,
            metadata={
                "gitbook_revision": raw_document.get("revision"),
                "slug": raw_document.get("slug"),
                "page_type": raw_document.get("type", "document"),
                "visibility": container.metadata.get("visibility") if container else None,
                "raw_type": raw_document.get("type", "document"),
                "etag": raw_document.get("_etag") or metadata.etag,
            },
        )

    def _metadata(self, page: dict[str, Any], container_id: str) -> KnowledgeDocumentMetadata:
        identifier = str(page.get("id") or "")
        urls = page.get("urls") or {}
        container = self._containers.get(container_id)
        path = list(page.get("_path") or [])
        if not path:
            raw_path = str(page.get("path") or "").strip("/")
            path = [item for item in raw_path.split("/") if item]
            path.append(str(page.get("title") or identifier)) if not path else None
        return KnowledgeDocumentMetadata(
            id=identifier,
            container_id=container_id,
            parent_id=str(page.get("_parent_id") or page.get("parent") or "") or None,
            title=str(page.get("title") or identifier),
            original_url=str(urls.get("public") or urls.get("published") or urls.get("app") or ""),
            created_at=_datetime(page.get("createdAt")),
            updated_at=_datetime(page.get("updatedAt")),
            etag=str(page.get("etag") or page.get("eTag") or "") or None,
            has_children=bool(page.get("pages")),
            document_type=str(page.get("type") or "document"),
            path=path or [str(page.get("title") or identifier)],
            metadata={
                "slug": page.get("slug"),
                "space_id": container_id,
                "raw_type": page.get("type", "document"),
                "ancestors": list(page.get("_ancestors") or []),
                "position": page.get("position") or page.get("order"),
                "visibility": page.get("visibility")
                or (container.metadata.get("visibility") if container else None),
            },
        )

    def close(self) -> None:
        session = getattr(self.client, "session", None)
        if session is not None:
            session.headers.pop("Authorization", None)
        self.client.close()
        self.secret = ""
        self.config.access_token = SecretStr("")
