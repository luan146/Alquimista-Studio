from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..models import ConnectorCapabilities, ConnectorStatus, SourceConfig
from .base import KnowledgeSourceConnector

ConnectorFactory = Callable[..., KnowledgeSourceConnector]


@dataclass(frozen=True)
class ConnectorDescriptor:
    source_type: str
    display_name: str
    integration_name: str
    # Keep accepting legacy display strings while exposing a stable enum.
    status: ConnectorStatus | str
    implemented: bool
    capabilities: ConnectorCapabilities
    factory: ConnectorFactory | None = None
    configuration_fields: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    @property
    def status_code(self) -> ConnectorStatus:
        value = str(self.status)
        if value in {item.value for item in ConnectorStatus}:
            return ConnectorStatus(value)
        normalized = value.casefold()
        if "dispon" in normalized:
            return ConnectorStatus.AVAILABLE
        if "desenvolv" in normalized:
            return ConnectorStatus.DEVELOPMENT
        return ConnectorStatus.UNAVAILABLE

    @property
    def operational(self) -> bool:
        return self.status_code in {ConnectorStatus.AVAILABLE, ConnectorStatus.EXPERIMENTAL}


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
        return [
            item for item in self.all()
            if item.status_code in {ConnectorStatus.AVAILABLE, ConnectorStatus.EXPERIMENTAL}
            and item.implemented and item.factory
        ]

    def list_available(self) -> list[ConnectorDescriptor]:
        """Explicit registry API used by UI and diagnostics."""
        return self.available()

    def create(self, source: SourceConfig, **kwargs: Any) -> KnowledgeSourceConnector:
        descriptor = self.get(source.source_type)
        if not descriptor.operational or not descriptor.implemented or descriptor.factory is None:
            raise ValueError(
                f"A integração {descriptor.display_name} ainda está em desenvolvimento."
            )
        return descriptor.factory(source, **kwargs)


def default_registry() -> ConnectorRegistry:
    from .confluence import ConfluenceRestConnector
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
    )
    registry = ConnectorRegistry()
    registry.register(
        ConnectorDescriptor(
            source_type="confluence_rest",
            display_name="Confluence",
            integration_name="API REST oficial",
            status=ConnectorStatus.AVAILABLE,
            implemented=True,
            capabilities=capabilities,
            factory=ConfluenceRestConnector,
            configuration_fields=("base_url", "space_key", "auth_mode"),
            limitations=("Anexos são referenciados pelo Markdown.",),
        )
    )
    zendesk_descriptor = ConnectorDescriptor(
            source_type="zendesk_guide",
            display_name="Zendesk Guide",
            integration_name="Help Center API",
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
            factory=ZendeskGuideConnector,
            configuration_fields=("subdomain", "locale", "auth_mode"),
            limitations=("O fluxo OAuth interativo deve ser configurado externamente.",),
    )
    registry.register(
        ConnectorDescriptor(
            source_type="gitbook_api",
            display_name="GitBook",
            integration_name="API REST oficial",
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
            factory=NotionConnector,
            configuration_fields=("integration_token", "auth_mode"),
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
            factory=SharePointConnector,
            configuration_fields=("site_url", "auth_mode"),
        )
    )
    return registry
