from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote, urlparse

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


class GitHubDocsConfig(BaseModel):
    """Runtime configuration for GitHub Docs and Wikis."""

    model_config = ConfigDict(validate_assignment=True)

    repo: str  # "owner/repo"
    branch: str = "main"
    docs_path: str = "docs"
    access_token: SecretStr = SecretStr("")
    api_base_url: str = "https://api.github.com"

    @field_validator("repo")
    @classmethod
    def validate_repo(cls, value: str) -> str:
        value = value.strip().strip("/")
        if "/" not in value or len(value.split("/")) != 2:
            raise ValueError("Informe o repositório no formato 'owner/repo' (ex: facebook/react).")
        return value


class GitHubDocsConnector(KnowledgeSourceConnector):
    SOURCE_TYPE = "github_docs"
    API_BASE_URL = "https://api.github.com"

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
            raise ValueError("A configuração não pertence ao conector GitHub Docs.")

        self.source = source
        self.options = options
        self.markdown_options = markdown_options or MarkdownOptions()
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)

        repo = source.space_key or ""
        if not repo and source.base_url:
            parsed = urlparse(source.base_url)
            parts = [p for p in parsed.path.strip("/").split("/") if p]
            if len(parts) >= 2:
                repo = f"{parts[0]}/{parts[1]}"

        docs_path = source.root_value or source.connector_options.get("docs_path", "docs")
        branch = source.space_name or source.connector_options.get("branch", "main")

        self.config = GitHubDocsConfig(
            repo=repo or "owner/repo",
            branch=branch,
            docs_path=docs_path,
            access_token=SecretStr(secret),
        )

        headers: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if secret.strip():
            headers["Authorization"] = f"Bearer {secret.strip()}"

        self._injected_client = client is not None
        self.client = client or ApiHttpClient(
            self.API_BASE_URL,
            options,
            token=self.token,
            log=self.log,
            headers=headers,
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
            base_url=f"https://github.com/{self.config.repo}",
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_public_access=True,
            supports_updated_at=True,
            supports_bearer_token=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        data = self.client.get_json(f"/repos/{self.config.repo}")
        if not isinstance(data, dict) or "full_name" not in data:
            raise InvalidResponseError("Repositório GitHub não encontrado ou inacessível.")
        return {
            "repository": str(data.get("full_name")),
            "default_branch": str(data.get("default_branch") or self.config.branch),
            "spaces_visible": 1,
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        repo_id = self.config.repo.replace("/", "_")
        container = KnowledgeContainer(
            id=repo_id,
            key=self.config.repo,
            name=self.config.repo,
            description=f"Documentação do repositório {self.config.repo}",
            container_type="repository",
            source_type=self.SOURCE_TYPE,
        )
        self._containers[repo_id] = container
        return [container]

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        # Busca recursivamente a árvore do repositório via Git Trees API
        tree_data = self.client.get_json(
            f"/repos/{self.config.repo}/git/trees/{self.config.branch}",
            params={"recursive": "1"},
        )
        if not isinstance(tree_data, dict) or not isinstance(tree_data.get("tree"), list):
            raise InvalidResponseError("A API do GitHub não retornou a árvore de arquivos.")

        docs_prefix = self.config.docs_path.strip("/")
        documents: list[KnowledgeDocumentMetadata] = []

        for item in tree_data["tree"]:
            if not isinstance(item, dict) or item.get("type") != "blob":
                continue
            path = str(item.get("path") or "")
            if not path.lower().endswith((".md", ".markdown", ".mdx", ".txt")):
                continue
            if docs_prefix and not path.startswith(docs_prefix):
                continue

            file_sha = str(item.get("sha") or "")
            parts = path.split("/")
            title = parts[-1].rsplit(".", 1)[0].replace("-", " ").replace("_", " ").title()
            
            raw = {
                **item,
                "_container_id": container_id,
                "_title": title,
                "_path": parts,
                "_file_path": path,
            }
            self._documents[(container_id, file_sha)] = raw
            self._documents[(container_id, path)] = raw

            documents.append(
                KnowledgeDocumentMetadata(
                    id=file_sha,
                    container_id=container_id,
                    title=title,
                    original_url=f"https://github.com/{self.config.repo}/blob/{self.config.branch}/{path}",
                    etag=file_sha,
                    document_type="page",
                    path=parts,
                    metadata={"path": path, "sha": file_sha, "size": item.get("size")},
                )
            )

        return documents

    def get_document(
        self, document_id: str, container_id: str | None = None
    ) -> KnowledgeDocument:
        target_container = container_id or self.config.repo.replace("/", "_")
        meta = self._documents.get((target_container, document_id)) or {}
        file_path = meta.get("_file_path") or document_id

        # Baixa o conteúdo do arquivo via Raw Content
        raw_bytes = self.client.download(
            f"/repos/{self.config.repo}/contents/{quote(file_path, safe='/')}",
            params={"ref": self.config.branch},
            headers={"Accept": "application/vnd.github.raw+json"},
        )
        content_str = raw_bytes.decode("utf-8", errors="replace")
        title = meta.get("_title") or file_path.split("/")[-1].rsplit(".", 1)[0]

        container = self._containers.get(target_container)
        return KnowledgeDocument(
            id=document_id,
            container_id=target_container,
            title=title,
            content=normalize_markdown(content_str),
            original_url=f"https://github.com/{self.config.repo}/blob/{self.config.branch}/{file_path}",
            source_type=self.SOURCE_TYPE,
            container_name=container.name if container else self.config.repo,
            path=meta.get("_path") or [title],
            etag=meta.get("sha"),
            metadata={"path": file_path, "sha": meta.get("sha")},
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if not isinstance(raw_document, dict):
            raise TypeError("Documento bruto do GitHub Docs deve ser um objeto JSON.")
        doc_id = str(raw_document.get("id") or raw_document.get("sha") or "")
        container_id = str(raw_document.get("container_id") or raw_document.get("_container_id") or "github_repo")
        title = str(raw_document.get("title") or raw_document.get("_title") or "Documento GitHub")
        content = str(raw_document.get("content") or raw_document.get("markdown") or "")
        path_list = list(raw_document.get("path") or raw_document.get("_path") or [title])
        return KnowledgeDocument(
            id=doc_id,
            container_id=container_id,
            title=title,
            content=normalize_markdown(content),
            original_url=str(raw_document.get("original_url") or raw_document.get("html_url") or ""),
            source_type=self.SOURCE_TYPE,
            container_name=container_id,
            path=path_list,
            metadata=dict(raw_document.get("metadata") or {}),
        )

    def close(self) -> None:
        session = getattr(self.client, "session", None)
        if session is not None:
            session.headers.pop("Authorization", None)
        if hasattr(self, "client") and hasattr(self.client, "close"):
            self.client.close()
        self.secret = ""
        self.config.access_token = SecretStr("")
