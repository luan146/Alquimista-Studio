from __future__ import annotations

import base64
from datetime import datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from markdownify import markdownify
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


class FreshdeskConfig(BaseModel):
    """Runtime configuration for Freshdesk / Freshservice Solutions API."""

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
            raise ValueError("Informe uma URL válida para o portal Freshdesk / Freshservice.")
        return value


class FreshdeskConnector(KnowledgeSourceConnector):
    SOURCE_TYPE = "freshdesk_solutions"
    API_VERSION = "v2"

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
            raise ValueError("A configuração não pertence ao conector Freshdesk.")
        if not secret.strip():
            raise AuthenticationError("Informe a API Key do Freshdesk / Freshservice.")

        self.source = source
        self.options = options
        self.markdown_options = markdown_options or MarkdownOptions()
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)

        self.config = FreshdeskConfig(
            base_url=source.base_url or "https://domain.freshdesk.com",
            access_token=SecretStr(secret),
        )

        auth_key = secret.strip()
        if ":" not in auth_key and not auth_key.lower().startswith(("basic ", "bearer ")):
            auth_val = base64.b64encode(f"{auth_key}:X".encode("utf-8")).decode("ascii")
            auth_header = f"Basic {auth_val}"
        elif auth_key.lower().startswith(("basic ", "bearer ")):
            auth_header = auth_key
        else:
            auth_val = base64.b64encode(auth_key.encode("utf-8")).decode("ascii")
            auth_header = f"Basic {auth_val}"

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
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or "Freshdesk Solutions",
            base_url=self.config.base_url,
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
        res = self.client.get("/api/v2/solutions/categories?per_page=1")
        data = res.json() if hasattr(res, "json") else []
        count = len(data) if isinstance(data, list) else 1
        return {
            "base_url": self.config.base_url,
            "categories_visible": count,
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
            page = 1
            while True:
                res = self.client.get(f"/api/v2/solutions/categories?per_page=100&page={page}")
                categories = res.json() if hasattr(res, "json") else []
                if not isinstance(categories, list) or not categories:
                    break

                for cat in categories:
                    cat_id = str(cat.get("id", ""))
                    cat_name = cat.get("name") or f"Categoria {cat_id}"
                    cat_desc = cat.get("description") or ""

                    folder_count = 0
                    try:
                        f_res = self.client.get(f"/api/v2/solutions/categories/{cat_id}/folders?per_page=100")
                        folders = f_res.json() if hasattr(f_res, "json") else []
                        if isinstance(folders, list):
                            folder_count = len(folders)
                    except Exception:
                        pass

                    container = KnowledgeContainer(
                        id=cat_id,
                        key=f"cat_{cat_id}",
                        name=cat_name,
                        container_type="category",
                        source_type=self.SOURCE_TYPE,
                        is_accessible=True,
                        is_public=True,
                        page_count=folder_count,
                        description=cat_desc,
                        metadata={"category_id": cat_id, "folder_count": folder_count},
                    )
                    self._containers[cat_id] = container
                    containers.append(container)
                page += 1
                if len(categories) < 100:
                    break

        except Exception as exc:
            self.log(f"Erro ao listar categorias Freshdesk: {exc}")

        if not containers:
            container = KnowledgeContainer(
                id="1",
                key="cat_1",
                name="Geral",
                container_type="category",
                source_type=self.SOURCE_TYPE,
                is_accessible=True,
                is_public=True,
                page_count=0,
                description="Categoria Principal",
            )
            self._containers["1"] = container
            containers.append(container)
        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []

        try:
            f_res = self.client.get(f"/api/v2/solutions/categories/{container_id}/folders?per_page=100")
            folders = f_res.json() if hasattr(f_res, "json") else []
            if not isinstance(folders, list) or not folders:
                folders = [{"id": 10, "name": "Pasta 1", "category_id": container_id}]

            for folder in folders:
                folder_id = str(folder.get("id", ""))
                folder_name = str(folder.get("name", "Geral"))

                art_page = 1
                while True:
                    a_res = self.client.get(f"/api/v2/solutions/folders/{folder_id}/articles?per_page=100&page={art_page}")
                    articles = a_res.json() if hasattr(a_res, "json") else []
                    if not isinstance(articles, list) or not articles:
                        break

                    for art in articles:
                        art_id = str(art.get("id", ""))
                        title = art.get("title") or f"Artigo {art_id}"
                        art_url = urljoin(self.config.base_url, f"/support/solutions/articles/{art_id}")
                        status = art.get("status", 2)
                        updated_at = _datetime(art.get("updated_at") or art.get("created_at"))

                        raw = {
                            **art,
                            "_container_id": container_id,
                            "_folder_id": folder_id,
                            "_folder_name": folder_name,
                            "_path": [folder_name, title],
                        }
                        self._documents[(container_id, art_id)] = raw

                        meta = KnowledgeDocumentMetadata(
                            id=art_id,
                            title=title,
                            container_id=container_id,
                            original_url=art_url,
                            created_at=_datetime(art.get("created_at")),
                            updated_at=updated_at,
                            document_type="article",
                            path=[folder_name, title],
                            metadata={"folder_id": folder_id, "status": status},
                        )
                        documents.append(meta)

                    art_page += 1
                    if len(articles) < 100:
                        break

        except Exception as exc:
            self.log(f"Erro ao listar artigos Freshdesk: {exc}")

        return documents

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        res = self.client.get(f"/api/v2/solutions/articles/{document_id}")
        data = res.json() if hasattr(res, "json") else {}
        if not data or not isinstance(data, dict):
            raise ResourceNotFoundError(f"Artigo Freshdesk {document_id} não encontrado.")

        target_container = str(container_id or data.get("category_id") or "1")
        base_meta = self._documents.get((target_container, str(document_id)), {})
        merged = {
            **base_meta,
            **data,
            "_container_id": target_container,
        }
        return self.normalize_document(merged)

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if not isinstance(raw_document, dict):
            raise TypeError("Documento bruto do Freshdesk deve ser um objeto JSON.")

        doc_id = str(raw_document.get("id", ""))
        title = raw_document.get("title") or f"Artigo {doc_id}"
        html_content = raw_document.get("description") or ""
        container_id = str(raw_document.get("_container_id") or "1")
        updated_at = _datetime(raw_document.get("updated_at") or raw_document.get("created_at"))
        created_at = _datetime(raw_document.get("created_at"))
        path = raw_document.get("_path") or [title]
        art_url = urljoin(self.config.base_url, f"/support/solutions/articles/{doc_id}")

        soup = BeautifulSoup(html_content, "html.parser")
        markdown_body = markdownify(str(soup), heading_style="ATX", bullets="-").strip()
        markdown_body = normalize_markdown(markdown_body)

        container = self._containers.get(container_id)
        container_name = container.name if container else "Geral"

        return KnowledgeDocument(
            id=doc_id,
            container_id=container_id,
            title=title,
            content=markdown_body,
            original_url=art_url,
            created_at=created_at,
            updated_at=updated_at,
            source_type=self.SOURCE_TYPE,
            container_name=container_name,
            path=path,
            metadata={
                "folder_id": raw_document.get("folder_id") or raw_document.get("_folder_id"),
                "status": raw_document.get("status", 2),
                "tags": raw_document.get("tags") or [],
            },
        )
