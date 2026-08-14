from __future__ import annotations

from alquimista.source_detection import detect_source_url
from alquimista.source_discovery import (
    DiscoveryStrategy,
    SourceDiscoveryService,
    detect_documentation_framework,
)


def test_detect_documentation_framework() -> None:
    html_docusaurus = '<div id="__docusaurus">Docusaurus App</div>'
    assert detect_documentation_framework(html_docusaurus) == "docusaurus"

    html_mkdocs = '<div class="md-content">MkDocs Material</div>'
    assert detect_documentation_framework(html_mkdocs) == "mkdocs"

    html_vitepress = '<div class="vp-doc">VitePress</div>'
    assert detect_documentation_framework(html_vitepress) == "vitepress"

    html_unknown = '<div>Site simples</div>'
    assert detect_documentation_framework(html_unknown) is None


def test_source_detection_for_expanded_platforms() -> None:
    assert detect_source_url("https://meusite.intercom.help").source_type == "intercom_api"
    assert detect_source_url("https://suaempresa.salesforce.com").source_type == "salesforce_api"
    assert detect_source_url("https://app.hubspot.com").source_type == "hubspot_api"
    assert detect_source_url("https://kb.helpjuice.com").source_type == "helpjuice_api"
    assert detect_source_url("https://app.getguru.com").source_type == "guru_api"
    assert detect_source_url("https://slite.com/workspace").source_type == "slite_api"
    assert detect_source_url("https://pt.wikipedia.org/wiki/Python").source_type == "mediawiki_api"
    assert detect_source_url("https://dash.readme.com/project/docs").source_type == "readme_api"
    assert detect_source_url("https://gitlab.com/gitlab-org/gitlab").source_type == "gitlab_docs"
    assert detect_source_url("https://blog.wordpress.com").source_type == "wordpress_api"
    assert detect_source_url("https://demo.ghost.io").source_type == "ghost_api"
    assert detect_source_url("C:\\Documentos\\Empresa").source_type == "local_files"


def test_discovery_service_closed_platform() -> None:
    svc = SourceDiscoveryService()
    try:
        res = svc.discover("https://empresa.atlassian.net/wiki/spaces/DEV")
        assert res.strategy == DiscoveryStrategy.OFFICIAL_API
        assert res.detected_source.source_type == "confluence_rest"
    finally:
        svc.close()
