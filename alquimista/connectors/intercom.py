from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

from bs4 import BeautifulSoup
from markdownify import markdownify

from ..errors import AuthenticationError
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
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value)
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


class IntercomConnector(KnowledgeSourceConnector):
    """Connector for Intercom Help Center articles and Customer Support conversations (Read-Only)."""

    SOURCE_TYPE = "intercom_api"
    BASE_URL = "https://api.intercom.io"

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
        if not secret.strip():
            raise AuthenticationError("Informe um Access Token (Bearer) do Intercom.")
        self.source = source
        self.options = options
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        self.client = client or ApiHttpClient(
            self.BASE_URL,
            options,
            token=self.token,
            log=self.log,
            headers={
                "Authorization": f"Bearer {secret}",
                "Intercom-Version": "2.11",
                "Accept": "application/json",
            },
        )
        self._containers: dict[str, KnowledgeContainer] = {}
        self._articles: dict[str, dict[str, Any]] = {}
        self._conversations: dict[str, dict[str, Any]] = {}

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or "Intercom",
            base_url=self.BASE_URL,
            connector_version="2.11",
        )

    def get_capabilities(self) -> ConnectorCapabilities:
        return ConnectorCapabilities(
            supports_collections=True,
            supports_hierarchy=True,
            supports_incremental_updates=True,
            supports_bearer_token=True,
            supports_updated_at=True,
            supports_support_records=True,
        )

    def validate_connection(self) -> dict[str, Any]:
        data = self.client.get_json("me")
        return {
            "identity": data.get("name") or data.get("email") or "Intercom Workspace",
            "type": data.get("type", "admin"),
            "auth": "Bearer Token",
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        containers: list[KnowledgeContainer] = []

        # 1. Help Center Collections
        try:
            col_data = self.client.get_json("help_center/collections")
            items = col_data.get("data") or col_data.get("collections") or []
            for col in items:
                cid = str(col.get("id"))
                name = str(col.get("name") or cid)
                container = KnowledgeContainer(
                    id=f"collection_{cid}",
                    key=f"collection_{cid}",
                    name=f"Help Center: {name}",
                    description=str(col.get("description") or ""),
                    container_type="knowledge_base",
                    source_type=self.SOURCE_TYPE,
                    updated_at=_datetime(col.get("updated_at")),
                )
                self._containers[container.id] = container
                containers.append(container)
        except Exception as exc:
            self.log(f"Intercom Help Center collections não disponíveis: {exc}")

        # 2. Support Conversations (Read-Only)
        conv_container = KnowledgeContainer(
            id="support_conversations",
            key="support_conversations",
            name="Atendimento: Conversas de Suporte",
            description="Histórico de conversas e mensagens de atendimento (Read-Only)",
            container_type="support_records",
            source_type=self.SOURCE_TYPE,
        )
        self._containers[conv_container.id] = conv_container
        containers.append(conv_container)

        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []

        if container_id == "support_conversations":
            # List support conversations
            try:
                data = self.client.get_json("conversations", params={"per_page": 50})
                items = data.get("conversations") or data.get("data") or []
                for conv in items:
                    cid = str(conv.get("id"))
                    title = f"Conversa #{cid}"
                    source = conv.get("source") or {}
                    if source.get("subject"):
                        title = f"Conversa #{cid} — {source.get('subject')}"
                    elif source.get("body"):
                        # Snippet
                        soup = BeautifulSoup(str(source.get("body")), "html.parser")
                        snippet = soup.get_text(" ", strip=True)[:60]
                        if snippet:
                            title = f"Conversa #{cid} — {snippet}"

                    raw_meta = {
                        "id": cid,
                        "title": title,
                        "created_at": _datetime(conv.get("created_at")),
                        "updated_at": _datetime(conv.get("updated_at")),
                        "state": conv.get("state"),
                        "read": conv.get("read"),
                    }
                    self._conversations[cid] = conv
                    documents.append(
                        KnowledgeDocumentMetadata(
                            id=cid,
                            container_id=container_id,
                            title=title,
                            created_at=raw_meta["created_at"],
                            updated_at=raw_meta["updated_at"],
                            document_type="conversation",
                            path=["Atendimento", title],
                            metadata=raw_meta,
                        )
                    )
            except Exception as exc:
                self.log(f"Erro ao listar conversas do Intercom: {exc}")
            return documents

        # Otherwise, Help Center Collection articles
        raw_col_id = container_id.replace("collection_", "")
        try:
            data = self.client.get_json("articles", params={"per_page": 50})
            items = data.get("data") or data.get("articles") or []
            for art in items:
                parent_id = str(art.get("parent_id") or "")
                if raw_col_id and parent_id and parent_id != raw_col_id:
                    continue
                aid = str(art.get("id"))
                title = str(art.get("title") or f"Artigo #{aid}")
                raw_meta = {
                    "id": aid,
                    "title": title,
                    "created_at": _datetime(art.get("created_at")),
                    "updated_at": _datetime(art.get("updated_at")),
                    "url": art.get("url") or "",
                }
                self._articles[aid] = art
                documents.append(
                    KnowledgeDocumentMetadata(
                        id=aid,
                        container_id=container_id,
                        title=title,
                        original_url=str(art.get("url") or ""),
                        created_at=raw_meta["created_at"],
                        updated_at=raw_meta["updated_at"],
                        document_type="article",
                        path=[container_id, title],
                        metadata=raw_meta,
                    )
                )
        except Exception as exc:
            self.log(f"Erro ao listar artigos do Intercom: {exc}")

        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        if container_id == "support_conversations":
            # Fetch conversation details
            data = self.client.get_json(f"conversations/{quote(document_id, safe='')}")
            conv = data if isinstance(data, dict) else {}
            title = f"Conversa #{document_id}"
            source = conv.get("source") or {}
            if source.get("subject"):
                title = f"Conversa #{document_id} — {source.get('subject')}"

            # Format conversation thread into structured Markdown
            thread_lines: list[str] = [
                f"# {title}",
                "",
                f"**ID da Conversa:** `{document_id}`  ",
                f"**Status:** `{conv.get('state', 'open')}`  ",
                f"**Criado em:** `{_datetime(conv.get('created_at'))}`  ",
                f"**Atualizado em:** `{_datetime(conv.get('updated_at'))}`  ",
                "",
                "## Mensagens",
                "",
            ]

            # Initial message
            author = source.get("author") or {}
            author_name = author.get("name") or author.get("email") or "Cliente"
            initial_body = source.get("body") or ""
            initial_md = markdownify(initial_body, heading_style="ATX").strip() if initial_body else "*(Sem mensagem)*"
            thread_lines.extend([
                f"### {author_name} ({_datetime(source.get('created_at')) or 'Início'}):",
                "",
                initial_md,
                "",
            ])

            # Conversation parts
            parts = (conv.get("conversation_parts") or {}).get("conversation_parts") or []
            for part in parts:
                p_author = part.get("author") or {}
                p_author_name = p_author.get("name") or p_author.get("email") or p_author.get("type", "Agente")
                p_body = part.get("body") or ""
                p_md = markdownify(p_body, heading_style="ATX").strip() if p_body else ""
                if p_md:
                    thread_lines.extend([
                        f"### {p_author_name} ({_datetime(part.get('created_at'))}):",
                        "",
                        p_md,
                        "",
                    ])

            content = normalize_markdown("\n".join(thread_lines))
            return KnowledgeDocument(
                id=document_id,
                container_id="support_conversations",
                title=title,
                content=content,
                source_type=self.SOURCE_TYPE,
                container_name="Conversas de Suporte",
                created_at=_datetime(conv.get("created_at")),
                updated_at=_datetime(conv.get("updated_at")),
                path=["Atendimento", title],
                metadata={
                    "raw_type": "conversation",
                    "state": conv.get("state"),
                    "assignee": (conv.get("assignee") or {}).get("name"),
                },
            )

        # Fetch Article
        data = self.client.get_json(f"articles/{quote(document_id, safe='')}")
        article = data if isinstance(data, dict) else {}
        title = str(article.get("title") or f"Artigo #{document_id}")
        body_html = str(article.get("body") or "")
        content = normalize_markdown(markdownify(body_html, heading_style="ATX", bullets="-"))

        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or "help_center",
            title=title,
            content=content,
            original_url=str(article.get("url") or ""),
            source_type=self.SOURCE_TYPE,
            container_name=container_id or "Help Center",
            created_at=_datetime(article.get("created_at")),
            updated_at=_datetime(article.get("updated_at")),
            path=[container_id or "Help Center", title],
            metadata={
                "raw_type": "article",
                "parent_id": article.get("parent_id"),
                "state": article.get("state"),
            },
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if isinstance(raw_document, dict):
            return KnowledgeDocument.model_validate(raw_document)
        raise TypeError("Documento bruto deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        self.secret = ""
        self.client.close()

