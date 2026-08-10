from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConnectorFormSpec:
    """Presentation metadata consumed by the source form."""

    url_label: str = "URL da fonte"
    url_placeholder: str = ""
    scope_label: str = "Contêiner"
    scope_placeholder: str = ""
    scope_name_label: str = "Nome do contêiner"
    supports_scope: bool = True
    supports_root: bool = False
    bearer_only: bool = False
    help_text: str = "A configuração será validada pela API oficial."


_SPECS: dict[str, ConnectorFormSpec] = {
    "confluence_rest": ConnectorFormSpec(
        url_label="URL do Confluence",
        url_placeholder="Cole a URL completa da página do Confluence",
        scope_label="Chave do espaço",
        scope_name_label="Nome do espaço",
        supports_scope=True,
        supports_root=True,
    ),
    "gitbook_api": ConnectorFormSpec(
        url_label="URL da API GitBook (opcional)",
        url_placeholder="https://api.gitbook.com/v1",
        scope_label="ID da organização GitBook",
        scope_placeholder="organizationId",
        scope_name_label="Nome da organização (opcional)",
        supports_scope=True,
        bearer_only=True,
        help_text="GitBook usa um Personal Access Token e descobre os espaços pela API oficial.",
    ),
    "zendesk_guide": ConnectorFormSpec(
        url_label="URL da API Zendesk (opcional)",
        url_placeholder="https://subdominio.zendesk.com/api/v2",
        scope_label="Subdomínio Zendesk",
        scope_placeholder="subdominio",
        scope_name_label="Locale (opcional)",
        supports_scope=True,
        bearer_only=True,
        help_text="Zendesk Guide usa um access token OAuth em modo Bearer e acessa somente o Help Center.",
    ),
    "notion_api": ConnectorFormSpec(
        url_label="URL do Notion / Integração",
        url_placeholder="https://api.notion.com/v1 ou cole a URL do workspace/página",
        scope_label="ID do Workspace / Database (opcional)",
        scope_placeholder="database_id",
        scope_name_label="Nome do workspace (opcional)",
        supports_scope=True,
        bearer_only=True,
        help_text="Notion usa um Integration Token (Internal/Public Integration) em modo Bearer para listar páginas e bancos de dados.",
    ),
    "sharepoint_graph": ConnectorFormSpec(
        url_label="URL do SharePoint / Microsoft Graph",
        url_placeholder="https://graph.microsoft.com/v1.0 ou URL do site SharePoint",
        scope_label="ID do Site SharePoint (opcional)",
        scope_placeholder="site_id",
        scope_name_label="Nome do site (opcional)",
        supports_scope=True,
        bearer_only=True,
        help_text="SharePoint utiliza o Microsoft Graph API com OAuth Access Token para listar e extrair bibliotecas e documentos.",
    ),
}


def form_spec(source_type: str) -> ConnectorFormSpec:
    return _SPECS.get(source_type, ConnectorFormSpec())
