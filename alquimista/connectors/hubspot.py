from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

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
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None


class HubSpotConnector(KnowledgeSourceConnector):
    """Connector for HubSpot Knowledge Base and Service Hub Tickets (Read-Only)."""

    SOURCE_TYPE = "hubspot_api"
    BASE_URL = "https://api.hubapi.com"

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
            raise AuthenticationError("Informe um Private App Access Token (Bearer) do HubSpot.")
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
                "Accept": "application/json",
            },
        )
        self._containers: dict[str, KnowledgeContainer] = {}

    def get_source_type(self) -> str:
        return self.SOURCE_TYPE

    def get_source(self) -> KnowledgeSource:
        return KnowledgeSource(
            id=self.source.id,
            source_type=self.SOURCE_TYPE,
            name=self.source.name or "HubSpot",
            base_url=self.BASE_URL,
            connector_version="v3",
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
        self.client.get_json("crm/v3/objects/tickets", params={"limit": 1})
        return {
            "connected": True,
            "auth": "Private App Access Token (Bearer)",
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        containers = [
            KnowledgeContainer(
                id="hubspot_knowledge",
                key="hubspot_knowledge",
                name="HubSpot Knowledge Base (Artigos)",
                description="Artigos de documentação e base de conhecimento",
                container_type="knowledge_base",
                source_type=self.SOURCE_TYPE,
            ),
            KnowledgeContainer(
                id="hubspot_tickets",
                key="hubspot_tickets",
                name="Service Hub: Tickets de Atendimento",
                description="Tickets e solicitações de clientes do Service Hub (Read-Only)",
                container_type="support_records",
                source_type=self.SOURCE_TYPE,
            ),
        ]
        for c in containers:
            self._containers[c.id] = c
        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []

        if container_id == "hubspot_tickets":
            try:
                data = self.client.get_json(
                    "crm/v3/objects/tickets",
                    params={
                        "limit": 100,
                        "properties": "subject,content,hs_ticket_category,hs_ticket_priority,hs_pipeline_stage,createdate,hs_lastmodifieddate",
                    },
                )
                results = data.get("results") or []
                for ticket in results:
                    tid = str(ticket.get("id"))
                    props = ticket.get("properties") or {}
                    subject = str(props.get("subject") or f"Ticket #{tid}")
                    title = f"Ticket #{tid} — {subject}"
                    documents.append(
                        KnowledgeDocumentMetadata(
                            id=tid,
                            container_id=container_id,
                            title=title,
                            created_at=_datetime(props.get("createdate")),
                            updated_at=_datetime(props.get("hs_lastmodifieddate")),
                            document_type="ticket",
                            path=["Tickets", title],
                            metadata=props,
                        )
                    )
            except Exception as exc:
                self.log(f"Erro ao consultar Tickets no HubSpot: {exc}")
            return documents

        # HubSpot Knowledge Base / Blog Posts
        try:
            data = self.client.get_json("cms/v3/blogs/posts", params={"limit": 100})
            posts = data.get("results") or []
            for post in posts:
                pid = str(post.get("id"))
                title = str(post.get("name") or post.get("title") or f"Artigo #{pid}")
                documents.append(
                    KnowledgeDocumentMetadata(
                        id=pid,
                        container_id=container_id,
                        title=title,
                        original_url=str(post.get("url") or ""),
                        created_at=_datetime(post.get("created")),
                        updated_at=_datetime(post.get("updated")),
                        document_type="article",
                        path=["Knowledge", title],
                        metadata=post,
                    )
                )
        except Exception as exc:
            self.log(f"Erro ao consultar Knowledge Base no HubSpot: {exc}")

        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        if container_id == "hubspot_tickets":
            data = self.client.get_json(
                f"crm/v3/objects/tickets/{quote(document_id, safe='')}",
                params={"properties": "subject,content,hs_ticket_category,hs_ticket_priority,hs_pipeline_stage,createdate,hs_lastmodifieddate"},
            )
            props = data.get("properties") or {}
            subject = str(props.get("subject") or f"Ticket #{document_id}")
            title = f"Ticket #{document_id} — {subject}"
            body_text = str(props.get("content") or "*(Sem descrição adicional)*")

            lines = [
                f"# {title}",
                "",
                f"**ID do Ticket:** `{document_id}`  ",
                f"**Estágio/Status:** `{props.get('hs_pipeline_stage', '')}`  ",
                f"**Prioridade:** `{props.get('hs_ticket_priority', '')}`  ",
                f"**Categoria:** `{props.get('hs_ticket_category', '')}`  ",
                f"**Criado em:** `{_datetime(props.get('createdate'))}`  ",
                f"**Última atualização:** `{_datetime(props.get('hs_lastmodifieddate'))}`  ",
                "",
                "## Descrição do Ticket",
                "",
                body_text,
            ]
            content = normalize_markdown("\n".join(lines))
            return KnowledgeDocument(
                id=document_id,
                container_id="hubspot_tickets",
                title=title,
                content=content,
                source_type=self.SOURCE_TYPE,
                container_name="Tickets de Atendimento",
                created_at=_datetime(props.get("createdate")),
                updated_at=_datetime(props.get("hs_lastmodifieddate")),
                path=["Tickets", title],
                metadata={
                    "raw_type": "ticket",
                    "priority": props.get("hs_ticket_priority"),
                    "stage": props.get("hs_pipeline_stage"),
                },
            )

        # Knowledge Post / Article
        data = self.client.get_json(f"cms/v3/blogs/posts/{quote(document_id, safe='')}")
        post = data if isinstance(data, dict) else {}
        title = str(post.get("name") or post.get("title") or f"Artigo #{document_id}")
        html = str(post.get("postBody") or post.get("post_body") or "")
        content = normalize_markdown(markdownify(html, heading_style="ATX", bullets="-"))

        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or "hubspot_knowledge",
            title=title,
            content=content,
            original_url=str(post.get("url") or ""),
            source_type=self.SOURCE_TYPE,
            container_name="HubSpot Knowledge Base",
            created_at=_datetime(post.get("created")),
            updated_at=_datetime(post.get("updated")),
            path=["Knowledge", title],
            metadata=post,
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if isinstance(raw_document, dict):
            return KnowledgeDocument.model_validate(raw_document)
        raise TypeError("Documento bruto do HubSpot deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        self.secret = ""
        self.client.close()

