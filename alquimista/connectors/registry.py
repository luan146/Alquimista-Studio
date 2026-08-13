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


@dataclass(frozen=True)
class ConnectorDescriptor:
    source_type: str
    display_name: str
    integration_name: str
    # Keep accepting legacy display strings while exposing a stable enum.
    status: ConnectorStatus | str
    implemented: bool
    capabilities: ConnectorCapabilities
    form: ConnectorFormSpec = ConnectorFormSpec()
    card: ConnectorCardSpec = ConnectorCardSpec()
    factory: ConnectorFactory | None = None
    configuration_fields: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

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

    def create(self, source: SourceConfig, **kwargs: Any) -> KnowledgeSourceConnector:
        descriptor = self.get(source.source_type)
        if not descriptor.runnable:
            raise ValueError(
                f"A integração {descriptor.display_name} ainda está em desenvolvimento."
            )
        assert descriptor.factory is not None
        return descriptor.factory(source, **kwargs)


def default_registry() -> ConnectorRegistry:
    from .confluence import ConfluenceRestConnector
    from .generic_web import GenericWebConnector
    from .gitbook import GitBookConnector
    from .notion import NotionConnector
    from .sharepoint import SharePointConnector
    from .zendesk import ZendeskGuideConnector

    capabilities = ConnectorCapabilities(
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
    )
    registry = ConnectorRegistry()
    registry.register(
        ConnectorDescriptor(
            source_type="confluence_rest",
            display_name="Confluence",
            integration_name="API REST oficial do Confluence",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            capabilities=capabilities,
            form=ConnectorFormSpec(
                url_label="URL do Confluence",
                url_placeholder="Cole a URL completa da página do Confluence",
                scope_label="Chave do espaço",
                scope_name_label="Nome do espaço",
                supports_scope=True,
                supports_root=True,
            ),
            card=ConnectorCardSpec(
                description=(
                    "Acesse páginas, espaços\ne documentos do Atlassian Confluence."
                ),
                icon=11,
                accent="#67B7FF",
                order=1,
                visible=True,
            ),
            factory=ConfluenceRestConnector,
            configuration_fields=("base_url", "space_key", "auth_mode"),
            limitations=("Anexos são referenciados pelo Markdown.",),
        )
    )
    zendesk_descriptor = ConnectorDescriptor(
        source_type="zendesk_guide",
        display_name="Zendesk Guide",
        integration_name="Help Center API do Zendesk",
        status=ConnectorStatus.AVAILABLE,
        implemented=True,
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
            help_text=(
                "Zendesk Guide usa um access token OAuth em modo Bearer e acessa "
                "somente o Help Center."
            ),
        ),
        card=ConnectorCardSpec(
            title="Zendesk",
            description=(
                "Conecte e extraia artigos,\ntickets e soluções do Zendesk Guide."
            ),
            icon=10,
            accent="#7FE4B5",
            order=0,
            visible=True,
        ),
        factory=ZendeskGuideConnector,
        configuration_fields=("subdomain", "locale", "auth_mode"),
        limitations=("O fluxo OAuth interativo deve ser configurado externamente.",),
    )
    registry.register(
        ConnectorDescriptor(
            source_type="gitbook_api",
            display_name="GitBook",
            integration_name="API REST oficial do GitBook",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
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
                scope_placeholder="organizationId",
                scope_name_label="Nome da organização (opcional)",
                supports_scope=True,
                bearer_only=True,
                help_text=(
                    "GitBook usa um Personal Access Token e descobre os espaços "
                    "pela API oficial."
                ),
            ),
            card=ConnectorCardSpec(
                description=(
                    "Importe documentação e conteúdos\n"
                    "disponíveis na sua base do GitBook."
                ),
                icon=14,
                accent="#B09AFF",
                order=4,
                visible=True,
            ),
            factory=GitBookConnector,
            configuration_fields=("organization_id", "auth_mode"),
            limitations=("Anexos não são baixados pelo conector.",),
        )
    )
    registry.register(zendesk_descriptor)
    registry.register(
        ConnectorDescriptor(
            source_type="notion_api",
            display_name="Notion",
            integration_name="API oficial do Notion",
            status=ConnectorStatus.EXPERIMENTAL,
            implemented=True,
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
                url_placeholder=(
                    "https://api.notion.com/v1 ou cole a URL do workspace/página"
                ),
                scope_label="ID do Workspace / Database (opcional)",
                scope_placeholder="database_id",
                scope_name_label="Nome do workspace (opcional)",
                supports_scope=True,
                bearer_only=True,
                help_text=(
                    "Notion usa um Integration Token (Internal/Public Integration) "
                    "em modo Bearer para listar páginas e bancos de dados."
                ),
            ),
            card=ConnectorCardSpec(
                description="Importe páginas, bases de dados\ne conteúdos do Notion.",
                icon=12,
                accent="#B09AFF",
                order=2,
                visible=True,
            ),
            factory=NotionConnector,
            configuration_fields=("auth_mode",),
            limitations=("Somente leitura; páginas e data sources.",),
        )
    )
    registry.register(
        ConnectorDescriptor(
            source_type="generic_web",
            display_name="Generic Web",
            integration_name="Página Web estática pública",
            status=ConnectorStatus.EXPERIMENTAL,
            implemented=True,
            capabilities=ConnectorCapabilities(
                supports_collections=True,
                supports_incremental_updates=True,
                supports_public_access=True,
                supports_updated_at=True,
            ),
            form=ConnectorFormSpec(
                url_label="URL HTTPS pública",
                url_placeholder="https://exemplo.com/documentacao",
                supports_scope=False,
                help_text="Uma página estática por URL; sem login, cookies ou crawling.",
            ),
            card=ConnectorCardSpec(
                description="Extraia uma página HTML pública estática.",
                icon=15,
                accent="#75C8FF",
                order=5,
                visible=True,
            ),
            factory=GenericWebConnector,
            configuration_fields=(),
            limitations=("Somente HTTPS público; assets são referenciados, não baixados.",),
        )
    )
    registry.register(
        ConnectorDescriptor(
            source_type="sharepoint_graph",
            display_name="SharePoint",
            integration_name="Microsoft Graph API",
            status=ConnectorStatus.DEVELOPMENT,
            implemented=False,
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
                url_placeholder=(
                    "https://graph.microsoft.com/v1.0 ou URL do site SharePoint"
                ),
                scope_label="ID do Site SharePoint (opcional)",
                scope_placeholder="site_id",
                scope_name_label="Nome do site (opcional)",
                supports_scope=True,
                bearer_only=True,
                help_text=(
                    "SharePoint utiliza o Microsoft Graph API com OAuth Access Token "
                    "para listar e extrair bibliotecas e documentos."
                ),
            ),
            card=ConnectorCardSpec(
                description=(
                    "Explore sites, bibliotecas e documentos\n"
                    "do Microsoft SharePoint."
                ),
                icon=13,
                accent="#75E7BA",
                order=3,
                visible=True,
            ),
            factory=SharePointConnector,
            configuration_fields=("site_url", "auth_mode"),
        )
    )
    return registry
