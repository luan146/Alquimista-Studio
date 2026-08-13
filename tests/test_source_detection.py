import pytest

from alquimista.source_detection import detect_source_url


@pytest.mark.parametrize(
    ("url", "source_type", "api_name"),
    [
        (
            "https://docs.example.com/display/DOC/Manual+interno",
            "confluence_rest",
            "API REST oficial do Confluence",
        ),
        ("https://acme.zendesk.com/hc/pt-br", "zendesk_guide", "Help Center API do Zendesk"),
        ("https://www.notion.so/acme/Manual-123", "notion_api", "API oficial do Notion"),
        (
            "https://acme.sharepoint.com/sites/manual",
            "sharepoint_graph",
            "Microsoft Graph API",
        ),
        ("https://docs.gitbook.io/manual", "gitbook_api", "API REST oficial do GitBook"),
    ],
)
def test_detect_source_url_identifies_platform_and_api(
    url: str, source_type: str, api_name: str
) -> None:
    detected = detect_source_url(url)

    assert detected.source_type == source_type
    assert detected.api_name == api_name


def test_detect_source_url_falls_back_to_generic_web() -> None:
    detected = detect_source_url("https://example.org/manual")
    assert detected.source_type == "generic_web"
