from __future__ import annotations

import base64
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

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


class GitLabDocsConnector(KnowledgeSourceConnector):
    """Connector for GitLab Project Wikis and Repository Markdown documentation."""

    SOURCE_TYPE = "gitlab_docs"
    DEFAULT_HOST = "https://gitlab.com"

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

        base_url = source.base_url.rstrip("/")
        if not base_url:
            base_url = self.DEFAULT_HOST
        parsed = urlsplit(base_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        self.origin = origin

        # Space key is project path or ID (e.g. "gitlab-org/gitlab" or "12345")
        self.project_id = str(source.space_key or source.connector_options.get("project_id") or parsed.path.strip("/")).strip("/")
        if not self.project_id and parsed.path.strip("/"):
            self.project_id = parsed.path.strip("/")

        headers: dict[str, str] = {"Accept": "application/json"}
        if secret.strip():
            headers["PRIVATE-TOKEN"] = secret

        self.client = client or ApiHttpClient(
            self.origin,
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
            name=self.source.name or f"GitLab ({self.project_id})",
            base_url=self.origin,
            connector_version="v4",
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

    def _encoded_project(self) -> str:
        return quote(self.project_id, safe="")

    def validate_connection(self) -> dict[str, Any]:
        data = self.client.get_json(f"api/v4/projects/{self._encoded_project()}")
        return {
            "name": data.get("name_with_namespace") or data.get("name") or self.project_id,
            "web_url": data.get("web_url", ""),
            "wiki_enabled": data.get("wiki_enabled", True),
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        return [
            KnowledgeContainer(
                id="wiki",
                key="wiki",
                name="GitLab Wiki",
                description="Páginas wiki do projeto GitLab",
                container_type="wiki",
                source_type=self.SOURCE_TYPE,
            ),
            KnowledgeContainer(
                id="repository",
                key="repository",
                name="Repositório (Docs Markdown)",
                description="Arquivos Markdown presentes no repositório",
                container_type="repository",
                source_type=self.SOURCE_TYPE,
            ),
        ]

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []

        if container_id == "wiki":
            try:
                wikis = self.client.get_json(f"api/v4/projects/{self._encoded_project()}/wikis")
                if isinstance(wikis, list):
                    for w in wikis:
                        slug = str(w.get("slug"))
                        title = str(w.get("title") or slug)
                        documents.append(
                            KnowledgeDocumentMetadata(
                                id=slug,
                                container_id="wiki",
                                title=title,
                                document_type="wiki_page",
                                path=["Wiki", title],
                                metadata=w,
                            )
                        )
            except Exception as exc:
                self.log(f"Erro ao listar wikis do GitLab: {exc}")
            return documents

        # Repository Markdown files
        try:
            tree = self.client.get_json(
                f"api/v4/projects/{self._encoded_project()}/repository/tree",
                params={"recursive": True, "per_page": 100},
            )
            if isinstance(tree, list):
                for item in tree:
                    path = str(item.get("path") or "")
                    if path.lower().endswith((".md", ".markdown", ".mdx", ".txt")):
                        name = item.get("name") or Path(path).name
                        documents.append(
                            KnowledgeDocumentMetadata(
                                id=path,
                                container_id="repository",
                                title=name,
                                document_type="repo_file",
                                path=["Repositório", *path.split("/")],
                                metadata=item,
                            )
                        )
        except Exception as exc:
            self.log(f"Erro ao listar repositório do GitLab: {exc}")

        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        if container_id == "wiki":
            data = self.client.get_json(f"api/v4/projects/{self._encoded_project()}/wikis/{quote(document_id, safe='')}")
            w = data if isinstance(data, dict) else {}
            title = str(w.get("title") or document_id)
            content = normalize_markdown(str(w.get("content") or ""))
            return KnowledgeDocument(
                id=document_id,
                container_id="wiki",
                title=title,
                content=content,
                source_type=self.SOURCE_TYPE,
                container_name="GitLab Wiki",
                path=["Wiki", title],
                metadata=w,
            )

        # Repository file
        data = self.client.get_json(
            f"api/v4/projects/{self._encoded_project()}/repository/files/{quote(document_id, safe='')}",
            params={"ref": "main"},
        )
        file_obj = data if isinstance(data, dict) else {}
        b64_content = file_obj.get("content") or ""
        try:
            text = base64.b64decode(b64_content).decode("utf-8", errors="replace")
        except Exception:
            text = b64_content

        title = Path(document_id).name
        content = normalize_markdown(text)
        return KnowledgeDocument(
            id=document_id,
            container_id="repository",
            title=title,
            content=content,
            source_type=self.SOURCE_TYPE,
            container_name="Repositório",
            path=["Repositório", *document_id.split("/")],
            metadata=file_obj,
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if isinstance(raw_document, dict):
            return KnowledgeDocument.model_validate(raw_document)
        raise TypeError("Documento bruto do GitLab deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        self.secret = ""
        self.client.close()

