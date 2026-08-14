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


class SalesforceConnector(KnowledgeSourceConnector):
    """Connector for Salesforce Knowledge articles and Service Cloud Cases (Read-Only)."""

    SOURCE_TYPE = "salesforce_api"
    API_VERSION = "v60.0"

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
            raise AuthenticationError("Informe um Access Token OAuth (Bearer) do Salesforce.")
        self.source = source
        self.options = options
        self.secret = secret
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)

        base_url = source.base_url.rstrip("/")
        if not base_url:
            base_url = "https://login.salesforce.com"
        self.base_url = base_url

        self.client = client or ApiHttpClient(
            self.base_url,
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
            name=self.source.name or "Salesforce",
            base_url=self.base_url,
            connector_version=self.API_VERSION,
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
        data = self.client.get_json(f"/services/data/{self.API_VERSION}/sobjects")
        return {
            "sobjects_count": len(data.get("sobjects") or []),
            "version": self.API_VERSION,
            "auth": "OAuth Bearer Token",
        }

    def list_containers(self) -> list[KnowledgeContainer]:
        containers = [
            KnowledgeContainer(
                id="salesforce_knowledge",
                key="salesforce_knowledge",
                name="Salesforce Knowledge (Artigos)",
                description="Artigos de conhecimento e documentações da base Salesforce",
                container_type="knowledge_base",
                source_type=self.SOURCE_TYPE,
            ),
            KnowledgeContainer(
                id="salesforce_cases",
                key="salesforce_cases",
                name="Service Cloud: Cases de Atendimento",
                description="Casos de suporte, tickets e histórico de atendimento (Read-Only)",
                container_type="support_records",
                source_type=self.SOURCE_TYPE,
            ),
        ]
        for c in containers:
            self._containers[c.id] = c
        return containers

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        documents: list[KnowledgeDocumentMetadata] = []

        if container_id == "salesforce_cases":
            query = (
                "SELECT Id, CaseNumber, Subject, Description, Status, Priority, CreatedDate, LastModifiedDate "
                "FROM Case LIMIT 100"
            )
            try:
                data = self.client.get_json(
                    f"/services/data/{self.API_VERSION}/query",
                    params={"q": query},
                )
                records = data.get("records") or []
                for rec in records:
                    cid = str(rec.get("Id"))
                    case_num = str(rec.get("CaseNumber") or cid)
                    subject = str(rec.get("Subject") or "Sem assunto")
                    title = f"Case #{case_num} — {subject}"
                    documents.append(
                        KnowledgeDocumentMetadata(
                            id=cid,
                            container_id=container_id,
                            title=title,
                            created_at=_datetime(rec.get("CreatedDate")),
                            updated_at=_datetime(rec.get("LastModifiedDate")),
                            document_type="case",
                            path=["Cases", title],
                            metadata=rec,
                        )
                    )
            except Exception as exc:
                self.log(f"Erro ao consultar Cases no Salesforce: {exc}")
            return documents

        # Salesforce Knowledge
        query = (
            "SELECT Id, Title, Summary, UrlName, LastModifiedDate "
            "FROM Knowledge__kav WHERE PublishStatus='Online' AND IsLatestVersion=true LIMIT 100"
        )
        try:
            data = self.client.get_json(
                f"/services/data/{self.API_VERSION}/query",
                params={"q": query},
            )
            records = data.get("records") or []
            for rec in records:
                aid = str(rec.get("Id"))
                title = str(rec.get("Title") or f"Artigo #{aid}")
                documents.append(
                    KnowledgeDocumentMetadata(
                        id=aid,
                        container_id=container_id,
                        title=title,
                        updated_at=_datetime(rec.get("LastModifiedDate")),
                        document_type="article",
                        path=["Knowledge", title],
                        metadata=rec,
                    )
                )
        except Exception:
            # Fallback query for older Knowledge schemas
            try:
                data = self.client.get_json(f"/services/data/{self.API_VERSION}/knowledgeManagement/articles")
                articles = data.get("articles") or []
                for art in articles:
                    aid = str(art.get("id"))
                    title = str(art.get("title") or f"Artigo #{aid}")
                    documents.append(
                        KnowledgeDocumentMetadata(
                            id=aid,
                            container_id=container_id,
                            title=title,
                            document_type="article",
                            path=["Knowledge", title],
                            metadata=art,
                        )
                    )
            except Exception as exc2:
                self.log(f"Erro ao consultar Knowledge no Salesforce: {exc2}")

        return documents

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        if container_id == "salesforce_cases":
            # Fetch Case details and comments
            case_data = self.client.get_json(f"/services/data/{self.API_VERSION}/sobjects/Case/{quote(document_id, safe='')}")
            case_num = str(case_data.get("CaseNumber") or document_id)
            subject = str(case_data.get("Subject") or "Sem assunto")
            title = f"Case #{case_num} — {subject}"

            lines: list[str] = [
                f"# {title}",
                "",
                f"**Número do Case:** `{case_num}`  ",
                f"**Status:** `{case_data.get('Status', '')}`  ",
                f"**Prioridade:** `{case_data.get('Priority', '')}`  ",
                f"**Origem:** `{case_data.get('Origin', '')}`  ",
                f"**Criado em:** `{_datetime(case_data.get('CreatedDate'))}`  ",
                f"**Última atualização:** `{_datetime(case_data.get('LastModifiedDate'))}`  ",
                "",
                "## Descrição do Case",
                "",
                str(case_data.get("Description") or "*(Sem descrição)*"),
                "",
            ]

            # Query case comments
            try:
                comments_query = f"SELECT Id, CommentBody, CreatedDate, CreatedBy.Name FROM CaseComment WHERE ParentId='{document_id}' ORDER BY CreatedDate ASC"
                comments_data = self.client.get_json(f"/services/data/{self.API_VERSION}/query", params={"q": comments_query})
                comments = comments_data.get("records") or []
                if comments:
                    lines.extend(["## Comentários e Histórico de Atendimento", ""])
                    for comm in comments:
                        author = (comm.get("CreatedBy") or {}).get("Name") or "Atendente"
                        dt = _datetime(comm.get("CreatedDate"))
                        lines.extend([
                            f"### {author} ({dt}):",
                            "",
                            str(comm.get("CommentBody") or ""),
                            "",
                        ])
            except Exception:
                pass

            content = normalize_markdown("\n".join(lines))
            return KnowledgeDocument(
                id=document_id,
                container_id="salesforce_cases",
                title=title,
                content=content,
                source_type=self.SOURCE_TYPE,
                container_name="Cases de Atendimento",
                created_at=_datetime(case_data.get("CreatedDate")),
                updated_at=_datetime(case_data.get("LastModifiedDate")),
                path=["Cases", title],
                metadata={
                    "raw_type": "case",
                    "status": case_data.get("Status"),
                    "priority": case_data.get("Priority"),
                },
            )

        # Knowledge Article
        art_data = self.client.get_json(f"/services/data/{self.API_VERSION}/sobjects/Knowledge__kav/{quote(document_id, safe='')}")
        title = str(art_data.get("Title") or f"Artigo #{document_id}")
        body = str(art_data.get("ArticleBody") or art_data.get("Summary") or "")
        content = normalize_markdown(markdownify(body, heading_style="ATX", bullets="-"))

        return KnowledgeDocument(
            id=document_id,
            container_id=container_id or "salesforce_knowledge",
            title=title,
            content=content,
            source_type=self.SOURCE_TYPE,
            container_name="Salesforce Knowledge",
            created_at=_datetime(art_data.get("CreatedDate")),
            updated_at=_datetime(art_data.get("LastModifiedDate")),
            path=["Knowledge", title],
            metadata=art_data,
        )

    def get_document_children(self, document_id: str) -> list[KnowledgeDocumentMetadata]:
        del document_id
        return []

    def normalize_document(self, raw_document: object) -> KnowledgeDocument:
        if isinstance(raw_document, KnowledgeDocument):
            return raw_document
        if isinstance(raw_document, dict):
            return KnowledgeDocument.model_validate(raw_document)
        raise TypeError("Documento bruto do Salesforce deve ser um KnowledgeDocument ou dict.")

    def close(self) -> None:
        self.secret = ""
        self.client.close()

