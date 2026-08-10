from alquimista.confluence_url import parse_confluence_url


def test_parse_display_url_autofills_space_and_title() -> None:
    parsed = parse_confluence_url(
        "https://docs.example.com/display/DEMO/Getting+Started"
    )
    assert parsed.base_url == "https://docs.example.com"
    assert parsed.space_key == "DEMO"
    assert parsed.root_mode == "title"
    assert parsed.root_value == "Getting Started"
    assert not parsed.entire_space


def test_parse_page_id_query_and_cloud_url() -> None:
    query = parse_confluence_url(
        "https://example.test/pages/viewpage.action?pageId=123456"
    )
    assert query.root_mode == "id"
    assert query.page_id == "123456"

    cloud = parse_confluence_url(
        "https://example.atlassian.net/wiki/spaces/DOC/pages/987654/Manual"
    )
    assert cloud.base_url == "https://example.atlassian.net/wiki"
    assert cloud.space_key == "DOC"
    assert cloud.root_value == "987654"


def test_space_url_selects_space_without_domain_special_case() -> None:
    parsed = parse_confluence_url(
        "https://knowledge.example.org/spaces/DEMO/overview"
    )

    assert parsed.space_key == "DEMO"
    assert parsed.root_mode == "space"
    assert not parsed.entire_space


def test_page_id_without_space_is_resolved_later() -> None:
    parsed = parse_confluence_url(
        "https://docs.example.com/pages/viewpage.action?pageId=123456"
    )

    assert parsed.page_id == "123456"
    assert parsed.root_mode == "id"
    assert not parsed.entire_space
