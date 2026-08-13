from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote, urljoin, urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ..errors import AuthenticationError, InvalidResponseError, ResourceNotFoundError
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


class BookStackConfig(BaseModel):
    """Runtime configuration for the BookStack REST API."""

    model_config = ConfigDict(validate_assignment=True)

    base_url: str
    access_token: SecretStr
    page_size: int = Field(default=100, ge=1, le=500)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            value = f"https://{value}"
        parsed = urlparse(value)
        if not parsed.hostname:
            raise ValueError("Informe uma URL válida para a instância do BookStack.")
        if not value.endswith("/api"):
            value = f"{value}/api"
        return value


class BookStackConnector(KnowledgeSourceConnector):
    SOURCE_TYPE = "bookstack_api"
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
            raise ValueError("A configuração não pertence ao conector BookStack.")
        if not secret.strip():
            raise AuthenticationError("Informe o Token de API do BookStack (Token ID:Token Secret).")

        self.source = source
        self.options = options
        self.markdown_options = markdown_options or MarkdownOptions()
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)

        self.config = BookStackConfig(
            base_url=source.base_url or "https://wiki.example.com/api",
            access_token=SecretStr(secret),
        )

        auth_header = f"Token {secret}" if ":" in secret or not secret.lower().startswith(("bearer ", "token ")) else secret
        self._injected_client = client is not None
        self.client = client or ApiHttpClient(
            self.config.base_url,
            options,
            token=self.token,
            log=self.log,
            headers={"Authorization": auth_header},
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
            base_url=self.config.base_url,
            connector_version=self.API_VERSION,
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_permissions=True,
            supports_updated_at=True,
            supports_bearer_token=True,
            supports_search=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        data = self.client.get_json("/books", params={"count": 1})
        if not isinstance(data, dict) or "data" not in data:
            raise InvalidResponseError("A API do BookStack não retornou uma resposta de livros válida.")
        total_books = int(data.get("total") or len(data.get("data", [])))
        return {
            "base_url": self.config.base_url,
            "books_visible": total_books,
            "spaces_visible": total_books,
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        containers: list[KnowledgeContainer] = []
        offset = 0
        limit = self.config.page_size
        seen_ids: set[str] = set()

        while True:
            payload = self.client.get_json("/books", params={"count": limit, "offset": offset})
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise InvalidResponseError("A API do BookStack retornou uma listagem de livros inválida.")
            items = payload["data"]
            if not items:
                break
            for item in items:
                if not isinstance(item, dict) or not item.get("id"):
                    continue
                book_id = str(item["id"])
                if book_id in seen_ids:
                    continue
                seen_ids.add(book_id)
                name = str(item.get("name") or book_id)
                container = KnowledgeContainer(
                    id=book_id,
                    key=str(item.get("slug") or book_id),
                    name=name,
                    description=str(item.get("description") or "") or None,
                    container_type="book",
                    source_type=self.SOURCE_TYPE,
                    created_at=_datetime(item.get("created_at")),
                    updated_at=_datetime(item.get("updated_at")),
                    metadata={"slug": item.get("slug")},
                )
                self._containers[book_id] = container
                containers.append(container)

            offset += len(items)
            total = payload.get("total")
            if total is not None and offset >= int(total):
                break
            if len(items) < limit:
                break

        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        # Busca a árvore completa do livro
        data = self.client.get_json(f"/books/{quote(str(container_id), safe='')}")
        if not isinstance(data, dict):
            raise InvalidResponseError("A API do BookStack retornou detalhes inválidos para o livro.")

        book_name = str(data.get("name") or container_id)
        contents = data.get("contents") or []
        documents: list[KnowledgeDocumentMetadata] = []

        for item in contents:
            if not isinstance(item, dict) or not item.get("type"):
                continue
            itype = item.get("type")
            if itype == "page":
                page_id = str(item["id"])
                title = str(item.get("name") or page_id)
                raw = {
                    **item,
                    "_container_id": container_id,
                    "_book_name": book_name,
                    "_path": [book_name, title],
                }
                self._documents[(container_id, page_id)] = raw
                documents.append(self._metadata(raw, container_id))
            elif itype == "chapter":
                chapter_id = str(item["id"])
                chapter_name = str(item.get("name") or chapter_id)
                chapter_pages = item.get("pages") or []
                for cp in chapter_pages:
                    if not isinstance(cp, dict) or not cp.get("id"):
                        continue
                    page_id = str(cp["id"])
                    title = str(cp.get("name") or page_id)
                    raw = {
                        **cp,
                        "_container_id": container_id,
                        "_book_name": book_name,
                        "_chapter_id": chapter_id,
                        "_chapter_name": chapter_name,
                        "_path": [book_name, chapter_name, title],
                    }
                    self._documents[(container_id, page_id)] = raw
                    documents.append(self._metadata(raw, container_id))

        return documents

    def get_document(
        self, document_id: str, container_id: str | None = None
    ) -> KnowledgeDocument:
        raw_page = self.client.get_json(f"/pages/{quote(str(document_id), safe='')}")
        if not isinstance(raw_page, dict):
            raise InvalidResponseError("A API do BookStack retornou uma página inválida.")

        target_container = str(
            container_id
            or raw_page.get("book_id")
            or self.source.space_key
            or "book"
        )
        base_meta = self._documents.get((target_container, str(document_id)), {})
        merged = {
            **base_meta,
            **raw_page,
            "_container_id": target_container,
            "_etag": getattr(self.client, "last_response_headers", {}).get("etag"),
        }
        return self.normalize_document(merged)

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if not isinstance(raw_document, dict):
            raise TypeError("Documento bruto do BookStack deve ser um objeto JSON.")

        container_id = str(raw_document.get("_container_id") or raw_document.get("book_id") or self.source.space_key or "book")
        metadata = self._metadata(raw_document, container_id)

        # Prioriza Markdown nativo do BookStack
        content = ""
        if raw_document.get("markdown"):
            content = normalize_markdown(str(raw_document["markdown"]))
        elif raw_document.get("html"):
            soup = BeautifulSoup(str(raw_document["html"]), "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            content = normalize_markdown(markdownify(str(soup), heading_style="ATX", bullets="-"))
        else:
            content = str(raw_document.get("content") or f"# {metadata.title}\n\nDocumento BookStack.")

        container = self._containers.get(container_id)
        container_name = container.name if container else str(raw_document.get("_book_name") or container_id)

        return KnowledgeDocument(
            id=metadata.id,
            container_id=container_id,
            parent_id=metadata.parent_id,
            title=metadata.title,
            content=content,
            original_url=metadata.original_url,
            created_at=metadata.created_at,
            updated_at=metadata.updated_at,
            etag=metadata.etag,
            source_type=self.SOURCE_TYPE,
            container_name=container_name,
            path=metadata.path,
            metadata={
                "slug": raw_document.get("slug"),
                "book_id": raw_document.get("book_id") or container_id,
                "chapter_id": raw_document.get("chapter_id") or raw_document.get("_chapter_id"),
                "tags": raw_document.get("tags") or [],
                "raw_type": "page",
                "etag": raw_document.get("_etag") or metadata.etag,
            },
        )

    def _metadata(self, raw: dict[str, Any], container_id: str) -> KnowledgeDocumentMetadata:
        page_id = str(raw.get("id") or "")
        title = str(raw.get("name") or raw.get("title") or page_id)
        book_name = str(raw.get("_book_name") or container_id)
        chapter_id = str(raw.get("chapter_id") or raw.get("_chapter_id") or "")
        chapter_name = str(raw.get("_chapter_name") or "")

        path = list(raw.get("_path") or [])
        if not path:
            path = [book_name, chapter_name, title] if chapter_name else [book_name, title]

        ancestors: list[dict[str, str]] = []
        if chapter_name and chapter_id:
            ancestors.append({"id": chapter_id, "title": chapter_name})

        # URL da página no BookStack
        url = str(raw.get("url") or "")
        if not url and self.config.base_url:
            host_origin = self.config.base_url.removesuffix("/api")
            slug = raw.get("slug") or page_id
            url = f"{host_origin}/books/{container_id}/page/{slug}"

        return KnowledgeDocumentMetadata(
            id=page_id,
            container_id=container_id,
            parent_id=chapter_id or None,
            title=title,
            original_url=url,
            created_at=_datetime(raw.get("created_at")),
            updated_at=_datetime(raw.get("updated_at")),
            etag=str(raw.get("etag") or "") or None,
            document_type="page",
            path=path,
            metadata={
                "slug": raw.get("slug"),
                "book_id": container_id,
                "chapter_id": chapter_id or None,
                "ancestors": ancestors,
                "tags": raw.get("tags") or [],
            },
        )

    def close(self) -> None:
        session = getattr(self.client, "session", None)
        if session is not None:
            session.headers.pop("Authorization", None)
        if hasattr(self, "client") and hasattr(self.client, "close"):
            self.client.close()
        self.secret = ""
        self.config.access_token = SecretStr("")
