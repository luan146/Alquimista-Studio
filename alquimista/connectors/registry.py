from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..models import ConnectorCapabilities, ConnectorStatus, SourceConfig
from .base import KnowledgeSourceConnector

ConnectorFactory = Callable[..., KnowledgeSourceConnector]


@dataclass(frozen=True)
class ConnectorFormSpec:
    """Platform-neutral presentation metadata for source/auth forms."""

    url_label: str = "URL da fonte"
    url_placeholder: str = ""
    scope_label: str = "Contêiner"
    scope_placeholder: str = ""
    scope_name_label: str = "Nome do contêiner"
    supports_scope: bool = True
    supports_root: bool = False
    bearer_only: bool = False
    help_text: str = "A configuração será validada pela API oficial."


@dataclass(frozen=True)
class ConnectorCardSpec:
    """Platform-neutral presentation metadata for the dashboard card."""

    title: str = ""
    description: str = ""
    icon: int = 0
    accent: str = "#67B7FF"
    order: int = 100
    visible: bool = False
    category: str = "knowledge_base"


@dataclass(frozen=True)
class ConnectorDescriptor:
    source_type: str
    display_name: str
    integration_name: str
    status: ConnectorStatus | str
    implemented: bool
    capabilities: ConnectorCapabilities
    form: ConnectorFormSpec = ConnectorFormSpec()
    card: ConnectorCardSpec = ConnectorCardSpec()
    factory: ConnectorFactory | None = None
    configuration_fields: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    category: str = "knowledge_base"

    @property
    def status_code(self) -> ConnectorStatus:
        value = str(self.status)
        if value in {item.value for item in ConnectorStatus}:
            return ConnectorStatus(value)
        normalized = value.casefold()
        if "indispon" in normalized or "unavail" in normalized:
            return ConnectorStatus.UNAVAILABLE
        if "dispon" in normalized:
            return ConnectorStatus.AVAILABLE
        if "desenvolv" in normalized:
            return ConnectorStatus.DEVELOPMENT
        return ConnectorStatus.UNAVAILABLE

    @property
    def operational(self) -> bool:
        return self.status_code in {ConnectorStatus.AVAILABLE, ConnectorStatus.EXPERIMENTAL}

    @property
    def runnable(self) -> bool:
        return self.operational and self.implemented and self.factory is not None


class ConnectorRegistry:
    def __init__(self, descriptors: list[ConnectorDescriptor] | None = None) -> None:
        self._descriptors = {
            descriptor.source_type: descriptor
            for descriptor in descriptors or []
        }

    def register(self, descriptor: ConnectorDescriptor) -> None:
        self._descriptors[descriptor.source_type] = descriptor

    def get(self, source_type: str) -> ConnectorDescriptor:
        try:
            return self._descriptors[source_type]
        except KeyError as exc:
            raise ValueError(f"Conector não registrado: {source_type}") from exc

    def all(self) -> list[ConnectorDescriptor]:
        return list(self._descriptors.values())

    def available(self) -> list[ConnectorDescriptor]:
        return [item for item in self.all() if item.runnable]

    def list_available(self) -> list[ConnectorDescriptor]:
        """Explicit registry API used by UI and diagnostics."""
        return self.available()

    def by_category(self, category: str) -> list[ConnectorDescriptor]:
        return [item for item in self.all() if item.category == category or item.card.category == category]

    def create(self, source: SourceConfig, **kwargs: Any) -> KnowledgeSourceConnector:
        descriptor = self.get(source.source_type)
        if not descriptor.runnable:
            raise ValueError(
                f"A integração {descriptor.display_name} ainda está em desenvolvimento."
            )
        assert descriptor.factory is not None
        return descriptor.factory(source, **kwargs)


def default_registry() -> ConnectorRegistry:
    from .bookstack import BookStackConnector
    from .confluence import ConfluenceRestConnector
    from .contentful import ContentfulConnector
    from .document360 import Document360Connector
    from .freshdesk import FreshdeskConnector
    from .generic_docs import GenericDocsConnector
    from .generic_web import GenericWebConnector
    from .ghost import GhostConnector
    from .gitbook import GitBookConnector
    from .github_docs import GitHubDocsConnector
    from .gitlab import GitLabDocsConnector
    from .guru import GuruConnector
    from .helpjuice import HelpjuiceConnector
    from .helpscout import HelpScoutConnector
    from .hubspot import HubSpotConnector
    from .intercom import IntercomConnector
    from .local_files import LocalFilesConnector
    from .mediawiki import MediaWikiConnector
    from .notion import NotionConnector
    from .outline import OutlineConnector
    from .readme import ReadMeConnector
    from .salesforce import SalesforceConnector
    from .sanity import SanityConnector
    from .sharepoint import SharePointConnector
    from .slite import SliteConnector
    from .strapi import StrapiConnector
    from .wordpress import WordPressConnector
    from .zendesk import ZendeskGuideConnector

    registry = ConnectorRegistry()

    # 1. Confluence
    registry.register(
        ConnectorDescriptor(
            source_type="confluence_rest",
            display_name="Confluence",
            integration_name="API REST oficial do Confluence",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="knowledge_base",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_attachments=True,
                supports_permissions=True,
                supports_search=True,
                supports_updated_at=True,
                supports_public_access=True,
                supports_bearer_token=True,
                supports_lazy_discovery=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL do Confluence",
                url_placeholder="Cole a URL completa da página do Confluence",
                scope_label="Chave do espaço",
                scope_name_label="Nome do espaço",
                supports_scope=True,
                supports_root=True,
            ),
            card=ConnectorCardSpec(
                title="Confluence",
                description="Acesse páginas, espaços\ne documentos do Atlassian Confluence.",
                icon=11,
                accent="#67B7FF",
                order=1,
                visible=True,
                category="knowledge_base",
            ),
            factory=ConfluenceRestConnector,
            configuration_fields=("base_url", "space_key", "auth_mode"),
            limitations=("Anexos são referenciados pelo Markdown.",),
        )
    )

    # 2. Zendesk
    registry.register(
        ConnectorDescriptor(
            source_type="zendesk_guide",
            display_name="Zendesk",
            integration_name="Help Center API do Zendesk",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="customer_support",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_permissions=True,
                supports_updated_at=True,
                supports_bearer_token=True,
                supports_multiple_languages=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da API Zendesk (opcional)",
                url_placeholder="https://subdominio.zendesk.com/api/v2",
                scope_label="Subdomínio Zendesk",
                scope_placeholder="subdominio",
                scope_name_label="Locale (opcional)",
                supports_scope=True,
                bearer_only=True,
                help_text="Zendesk Guide usa um access token OAuth em modo Bearer.",
            ),
            card=ConnectorCardSpec(
                title="Zendesk",
                description="Conecte e extraia artigos,\ntickets e soluções do Zendesk Guide.",
                icon=10,
                accent="#7FE4B5",
                order=0,
                visible=True,
                category="customer_support",
            ),
            factory=ZendeskGuideConnector,
            configuration_fields=("subdomain", "locale", "auth_mode"),
        )
    )


    # 3. Notion
    registry.register(
        ConnectorDescriptor(
            source_type="notion_api",
            display_name="Notion",
            integration_name="API oficial do Notion",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="knowledge_base",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_permissions=True,
                supports_updated_at=True,
                supports_bearer_token=True,
                supports_search=True,
                supports_lazy_discovery=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL do Notion / Integração",
                url_placeholder="https://api.notion.com/v1 ou cole a URL do workspace/página",
                scope_label="ID do Workspace / Database (opcional)",
                scope_placeholder="database_id",
                scope_name_label="Nome do workspace (opcional)",
                supports_scope=True,
                bearer_only=True,
            ),
            card=ConnectorCardSpec(
                title="Notion",
                description="Importe páginas, bases de dados\ne conteúdos do Notion.",
                icon=12,
                accent="#B09AFF",
                order=2,
                visible=True,
                category="knowledge_base",
            ),
            factory=NotionConnector,
            configuration_fields=("auth_mode",),
        )
    )

    # 4. SharePoint
    registry.register(
        ConnectorDescriptor(
            source_type="sharepoint_graph",
            display_name="SharePoint",
            integration_name="Microsoft Graph API",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="knowledge_base",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_permissions=True,
                supports_updated_at=True,
                supports_bearer_token=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL do SharePoint / Microsoft Graph",
                url_placeholder="https://graph.microsoft.com/v1.0 ou URL do site SharePoint",
                scope_label="ID do Site SharePoint (opcional)",
                supports_scope=True,
                bearer_only=True,
            ),
            card=ConnectorCardSpec(
                title="SharePoint",
                description="Explore sites, bibliotecas e documentos\ndo Microsoft SharePoint.",
                icon=13,
                accent="#75E7BA",
                order=3,
                visible=True,
                category="knowledge_base",
            ),
            factory=SharePointConnector,
            configuration_fields=("site_url", "auth_mode"),
        )
    )

    # 5. GitBook
    registry.register(
        ConnectorDescriptor(
            source_type="gitbook_api",
            display_name="GitBook",
            integration_name="API REST oficial do GitBook",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="knowledge_base",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_permissions=True,
                supports_updated_at=True,
                supports_bearer_token=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da API GitBook (opcional)",
                url_placeholder="https://api.gitbook.com/v1",
                scope_label="ID da organização GitBook",
                supports_scope=True,
                bearer_only=True,
            ),
            card=ConnectorCardSpec(
                title="GitBook",
                description="Importe documentação e conteúdos\ndisponíveis na sua base do GitBook.",
                icon=14,
                accent="#B09AFF",
                order=4,
                visible=True,
                category="knowledge_base",
            ),
            factory=GitBookConnector,
            configuration_fields=("organization_id", "auth_mode"),
        )
    )

    # 6. Generic Web
    registry.register(
        ConnectorDescriptor(
            source_type="generic_web",
            display_name="Generic Web",
            integration_name="Página Web pública",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="web",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_incremental_updates=True,
                supports_public_access=True,
                supports_updated_at=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da Página Web (HTTP / HTTPS)",
                url_placeholder="https://exemplo.com/pagina",
                supports_scope=False,
            ),
            card=ConnectorCardSpec(
                title="Generic Web",
                description="Transforme qualquer página da internet em Markdown limpo.",
                icon=15,
                accent="#75C8FF",
                order=5,
                visible=True,
                category="web",
            ),
            factory=GenericWebConnector,
            configuration_fields=(),
        )
    )

    # 7. Generic Documentation & Frameworks
    registry.register(
        ConnectorDescriptor(
            source_type="generic_docs",
            display_name="Web Docs / Frameworks",
            integration_name="Descoberta Web (llms.txt / Sitemap / Docusaurus / MkDocs / Mintlify)",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="web",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_public_access=True,
                supports_updated_at=True,
                supports_sitemap=True,
                supports_llms_txt=True,
                supports_crawler=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da Documentação Web",
                url_placeholder="https://docs.exemplo.com",
                supports_scope=False,
                help_text="Descobre páginas automaticamente via llms.txt, sitemap.xml ou crawler interno.",
            ),
            card=ConnectorCardSpec(
                title="Web Docs",
                description="Descubra e extraia documentações criadas\ncom Docusaurus, MkDocs, Mintlify, VitePress, etc.",
                icon=15,
                accent="#38BDF8",
                order=6,
                visible=True,
                category="web",
            ),
            factory=GenericDocsConnector,
        )
    )

    # 8. Local Files & Folders
    registry.register(
        ConnectorDescriptor(
            source_type="local_files",
            display_name="Arquivos / Pastas Locais",
            integration_name="Importador Universal de Documentos Locais",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="files",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_attachments=True,
                supports_public_access=True,
                supports_updated_at=True,
                supports_local_files=True,
            ),
            form=ConnectorFormSpec(
                url_label="Caminho do Arquivo ou Pasta Local",
                url_placeholder="C:\\Documentos ou /home/usuario/docs",
                supports_scope=False,
                help_text="Converte PDF, Word, Excel, PowerPoint, EPUB, HTML, Imagens e Texto para Markdown.",
            ),
            card=ConnectorCardSpec(
                title="Arquivos Locais",
                description="Importe e converta arquivos e pastas locais\n(PDF, DOCX, XLSX, PPTX, EPUB, HTML) para Markdown.",
                icon=13,
                accent="#F59E0B",
                order=7,
                visible=True,
                category="files",
            ),
            factory=LocalFilesConnector,
        )
    )

    # 9. BookStack
    registry.register(
        ConnectorDescriptor(
            source_type="bookstack_api",
            display_name="BookStack",
            integration_name="API REST oficial do BookStack",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="knowledge_base",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_permissions=True,
                supports_updated_at=True,
                supports_bearer_token=True,
                supports_search=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da instância BookStack",
                url_placeholder="https://wiki.suaempresa.com",
                scope_label="ID ou Slug do Livro (opcional)",
                supports_scope=True,
                bearer_only=True,
            ),
            card=ConnectorCardSpec(
                title="BookStack",
                description="Extraia prateleiras, livros e capítulos\ndo BookStack Wiki.",
                icon=16,
                accent="#FFA857",
                order=8,
                visible=True,
                category="knowledge_base",
            ),
            factory=BookStackConnector,
            configuration_fields=("base_url", "auth_mode"),
        )
    )

    # 10. GitHub Docs
    registry.register(
        ConnectorDescriptor(
            source_type="github_docs",
            display_name="GitHub Docs / Wiki",
            integration_name="GitHub API oficial",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="developer",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_public_access=True,
                supports_updated_at=True,
                supports_bearer_token=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL do Repositório GitHub",
                url_placeholder="https://github.com/org/repo",
                scope_label="Repositório (owner/repo)",
                supports_scope=True,
            ),
            card=ConnectorCardSpec(
                title="GitHub",
                description="Importe documentações Markdown e Wikis\nde repositórios GitHub.",
                icon=17,
                accent="#E1E4E8",
                order=9,
                visible=True,
                category="developer",
            ),
            factory=GitHubDocsConnector,
            configuration_fields=("repo", "docs_path", "branch"),
        )
    )

    # 11. GitLab Docs
    registry.register(
        ConnectorDescriptor(
            source_type="gitlab_docs",
            display_name="GitLab Docs / Wiki",
            integration_name="GitLab API v4 oficial",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="developer",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_public_access=True,
                supports_bearer_token=True,
                supports_updated_at=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL do Projeto GitLab",
                url_placeholder="https://gitlab.com/org/projeto",
                scope_label="Projeto (caminho ou ID)",
                supports_scope=True,
            ),
            card=ConnectorCardSpec(
                title="GitLab",
                description="Importe wikis e documentações Markdown\nde projetos GitLab.",
                icon=17,
                accent="#FC6D26",
                order=10,
                visible=True,
                category="developer",
            ),
            factory=GitLabDocsConnector,
        )
    )

    # 12. Freshdesk
    registry.register(
        ConnectorDescriptor(
            source_type="freshdesk_solutions",
            display_name="Freshdesk",
            integration_name="Solutions API & Tickets",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="customer_support",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_updated_at=True,
                supports_bearer_token=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL do Portal Freshdesk",
                url_placeholder="https://empresa.freshdesk.com",
                supports_scope=True,
            ),
            card=ConnectorCardSpec(
                title="Freshdesk",
                description="Conecte categorias, pastas e artigos\ndo Freshdesk / Freshservice.",
                icon=12,
                accent="#25C974",
                order=11,
                visible=True,
                category="customer_support",
            ),
            factory=FreshdeskConnector,
        )
    )

    # 13. Intercom
    registry.register(
        ConnectorDescriptor(
            source_type="intercom_api",
            display_name="Intercom",
            integration_name="Intercom Help Center & Support API",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="customer_support",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_bearer_token=True,
                supports_updated_at=True,
                supports_support_records=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da Instância Intercom",
                url_placeholder="https://api.intercom.io",
                supports_scope=False,
                bearer_only=True,
                help_text="Acesse o Help Center e conversas de suporte do Intercom via Access Token.",
            ),
            card=ConnectorCardSpec(
                title="Intercom",
                description="Extraia artigos do Help Center e conversas\nde atendimento do Intercom.",
                icon=10,
                accent="#1F8CEB",
                order=12,
                visible=True,
                category="customer_support",
            ),
            factory=IntercomConnector,
        )
    )

    # 14. Salesforce
    registry.register(
        ConnectorDescriptor(
            source_type="salesforce_api",
            display_name="Salesforce",
            integration_name="Salesforce Knowledge & Service Cloud API",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="customer_support",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_bearer_token=True,
                supports_updated_at=True,
                supports_support_records=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da Instância Salesforce",
                url_placeholder="https://suaempresa.my.salesforce.com",
                supports_scope=False,
                bearer_only=True,
            ),
            card=ConnectorCardSpec(
                title="Salesforce",
                description="Conecte artigos Knowledge e Cases\nde atendimento do Salesforce.",
                icon=11,
                accent="#00A1E0",
                order=13,
                visible=True,
                category="customer_support",
            ),
            factory=SalesforceConnector,
        )
    )

    # 15. HubSpot
    registry.register(
        ConnectorDescriptor(
            source_type="hubspot_api",
            display_name="HubSpot",
            integration_name="HubSpot Knowledge Base & Service Hub API",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="customer_support",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_bearer_token=True,
                supports_updated_at=True,
                supports_support_records=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da API HubSpot",
                url_placeholder="https://api.hubapi.com",
                supports_scope=False,
                bearer_only=True,
            ),
            card=ConnectorCardSpec(
                title="HubSpot",
                description="Extraia artigos da base de conhecimento\ne tickets de atendimento do HubSpot.",
                icon=12,
                accent="#FF7A59",
                order=14,
                visible=True,
                category="customer_support",
            ),
            factory=HubSpotConnector,
        )
    )

    # 16. Help Scout
    registry.register(
        ConnectorDescriptor(
            source_type="helpscout_docs",
            display_name="Help Scout",
            integration_name="Docs API",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="customer_support",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_updated_at=True,
                supports_bearer_token=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da Base Docs do Help Scout",
                url_placeholder="https://docsapi.helpscout.net/v1",
                supports_scope=True,
            ),
            card=ConnectorCardSpec(
                title="Help Scout",
                description="Importe coleções e artigos\nda Base Docs do Help Scout.",
                icon=11,
                accent="#1292EE",
                order=15,
                visible=True,
                category="customer_support",
            ),
            factory=HelpScoutConnector,
        )
    )

    # 17. Document360
    registry.register(
        ConnectorDescriptor(
            source_type="document360_api",
            display_name="Document360",
            integration_name="REST API",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="knowledge_base",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_updated_at=True,
                supports_bearer_token=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da API Document360",
                url_placeholder="https://apihub.document360.io/v2",
                supports_scope=True,
                bearer_only=True,
            ),
            card=ConnectorCardSpec(
                title="Document360",
                description="Extraia categorias e artigos\ndo Document360 Knowledge Base.",
                icon=10,
                accent="#7C3AED",
                order=16,
                visible=True,
                category="knowledge_base",
            ),
            factory=Document360Connector,
        )
    )

    # 18. Outline
    registry.register(
        ConnectorDescriptor(
            source_type="outline_api",
            display_name="Outline",
            integration_name="Knowledge Base API",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="knowledge_base",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_updated_at=True,
                supports_bearer_token=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da Instância Outline",
                url_placeholder="https://app.getoutline.com",
                supports_scope=True,
                bearer_only=True,
            ),
            card=ConnectorCardSpec(
                title="Outline",
                description="Extraia coleções e documentações\ndo Outline Knowledge Base.",
                icon=14,
                accent="#0052CC",
                order=17,
                visible=True,
                category="knowledge_base",
            ),
            factory=OutlineConnector,
        )
    )

    # 19. Helpjuice
    registry.register(
        ConnectorDescriptor(
            source_type="helpjuice_api",
            display_name="Helpjuice",
            integration_name="Helpjuice Knowledge Base API",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="knowledge_base",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_bearer_token=True,
                supports_public_access=True,
                supports_updated_at=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da Base Helpjuice",
                url_placeholder="https://suaempresa.helpjuice.com",
                supports_scope=True,
            ),
            card=ConnectorCardSpec(
                title="Helpjuice",
                description="Extraia categorias e artigos de suporte\nda base de conhecimento Helpjuice.",
                icon=11,
                accent="#3B82F6",
                order=18,
                visible=True,
                category="knowledge_base",
            ),
            factory=HelpjuiceConnector,
        )
    )

    # 20. Guru
    registry.register(
        ConnectorDescriptor(
            source_type="guru_api",
            display_name="Guru",
            integration_name="Guru Knowledge Cards API",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="knowledge_base",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_bearer_token=True,
                supports_updated_at=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da API Guru",
                url_placeholder="https://api.getguru.com/api/v1",
                supports_scope=True,
            ),
            card=ConnectorCardSpec(
                title="Guru",
                description="Extraia coleções e cards de conhecimento\ndo Guru.",
                icon=12,
                accent="#10B981",
                order=19,
                visible=True,
                category="knowledge_base",
            ),
            factory=GuruConnector,
        )
    )

    # 21. Slite
    registry.register(
        ConnectorDescriptor(
            source_type="slite_api",
            display_name="Slite",
            integration_name="Slite Channels & Notes API",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="knowledge_base",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_bearer_token=True,
                supports_updated_at=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da API Slite",
                url_placeholder="https://api.slite.com/v1",
                supports_scope=True,
                bearer_only=True,
            ),
            card=ConnectorCardSpec(
                title="Slite",
                description="Importe canais e notas colaborativas\ndo Slite.",
                icon=14,
                accent="#6366F1",
                order=20,
                visible=True,
                category="knowledge_base",
            ),
            factory=SliteConnector,
        )
    )

    # 22. MediaWiki
    registry.register(
        ConnectorDescriptor(
            source_type="mediawiki_api",
            display_name="MediaWiki",
            integration_name="MediaWiki Action API (api.php)",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="knowledge_base",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_public_access=True,
                supports_updated_at=True,
                supports_search=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL do MediaWiki / api.php",
                url_placeholder="https://pt.wikipedia.org/w/api.php",
                supports_scope=True,
            ),
            card=ConnectorCardSpec(
                title="MediaWiki",
                description="Extraia artigos e categorias de instâncias\nMediaWiki e Wikipedia.",
                icon=16,
                accent="#000000",
                order=21,
                visible=True,
                category="knowledge_base",
            ),
            factory=MediaWikiConnector,
        )
    )

    # 23. ReadMe
    registry.register(
        ConnectorDescriptor(
            source_type="readme_api",
            display_name="ReadMe",
            integration_name="ReadMe Documentation API",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="developer",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_bearer_token=True,
                supports_updated_at=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da API ReadMe",
                url_placeholder="https://dash.readme.com/api/v1",
                supports_scope=True,
                bearer_only=True,
            ),
            card=ConnectorCardSpec(
                title="ReadMe",
                description="Importe categorias e documentações técnicas\nda plataforma ReadMe.",
                icon=17,
                accent="#00B4D8",
                order=22,
                visible=True,
                category="developer",
            ),
            factory=ReadMeConnector,
        )
    )

    # 24. WordPress
    registry.register(
        ConnectorDescriptor(
            source_type="wordpress_api",
            display_name="WordPress",
            integration_name="WordPress REST API v2",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="cms",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_public_access=True,
                supports_bearer_token=True,
                supports_updated_at=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL do Site WordPress",
                url_placeholder="https://seusite.com/wp-json/wp/v2",
                supports_scope=True,
            ),
            card=ConnectorCardSpec(
                title="WordPress",
                description="Extraia posts, artigos e páginas estáticas\nde sites WordPress.",
                icon=15,
                accent="#21759B",
                order=23,
                visible=True,
                category="cms",
            ),
            factory=WordPressConnector,
        )
    )

    # 25. Ghost
    registry.register(
        ConnectorDescriptor(
            source_type="ghost_api",
            display_name="Ghost",
            integration_name="Ghost Content API",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="cms",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_public_access=True,
                supports_updated_at=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL do Site Ghost",
                url_placeholder="https://seusite.ghost.io",
                supports_scope=True,
                bearer_only=True,
            ),
            card=ConnectorCardSpec(
                title="Ghost",
                description="Importe publicações e páginas\nde publicações Ghost.",
                icon=15,
                accent="#15171A",
                order=24,
                visible=True,
                category="cms",
            ),
            factory=GhostConnector,
        )
    )

    # 26. Strapi
    registry.register(
        ConnectorDescriptor(
            source_type="strapi_api",
            display_name="Strapi",
            integration_name="Strapi Headless CMS API",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="cms",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_bearer_token=True,
                supports_public_access=True,
                supports_updated_at=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da Instância Strapi",
                url_placeholder="https://strapi.seusite.com/api",
                scope_label="Nome da Coleção (ex.: articles)",
                supports_scope=True,
            ),
            card=ConnectorCardSpec(
                title="Strapi",
                description="Extraia coleções e conteúdo estruturado\ndo Strapi Headless CMS.",
                icon=12,
                accent="#4945FF",
                order=25,
                visible=True,
                category="cms",
            ),
            factory=StrapiConnector,
        )
    )

    # 27. Contentful
    registry.register(
        ConnectorDescriptor(
            source_type="contentful_api",
            display_name="Contentful",
            integration_name="Contentful Content Delivery API",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="cms",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_bearer_token=True,
                supports_updated_at=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL da API Contentful",
                url_placeholder="https://cdn.contentful.com",
                scope_label="Space ID",
                supports_scope=True,
                bearer_only=True,
            ),
            card=ConnectorCardSpec(
                title="Contentful",
                description="Importe modelos de conteúdo e entradas\ndo Contentful.",
                icon=14,
                accent="#2D7FF9",
                order=26,
                visible=True,
                category="cms",
            ),
            factory=ContentfulConnector,
        )
    )

    # 28. Sanity
    registry.register(
        ConnectorDescriptor(
            source_type="sanity_api",
            display_name="Sanity",
            integration_name="Sanity GROQ Query API",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            category="cms",
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_hierarchy=True,
                supports_incremental_updates=True,
                supports_public_access=True,
                supports_bearer_token=True,
                supports_updated_at=True,
            ),
            form=ConnectorFormSpec(
                url_label="Project ID do Sanity",
                url_placeholder="ex.: abcdef12",
                scope_label="Project ID",
                scope_name_label="Dataset (padrão: production)",
                supports_scope=True,
            ),
            card=ConnectorCardSpec(
                title="Sanity",
                description="Consulte e extraia documentos do Sanity\nContent Lake via GROQ.",
                icon=10,
                accent="#F03E2F",
                order=27,
                visible=True,
                category="cms",
            ),
            factory=SanityConnector,
        )
    )

    return registry
