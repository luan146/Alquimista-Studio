from __future__ import annotations

from typing import Any

import pytest

from alquimista.browser.adapters import ConnectorDiscoveryAdapter, DiscoveryCapabilityError
from alquimista.browser.contracts import Visibility
from alquimista.connectors import ConfluenceRestConnector
from alquimista.errors import ResourceNotFoundError
from alquimista.models import ExtractionOptions, SourceConfig


class Response:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.status_code = 200
        self.headers: dict[str, str] = {}
        self.payload = payload

    def json(self) -> dict[str, Any]:
        return self.payload

    def raise_for_status(self) -> None:
        return None


class Session:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self.responses = list(responses)
        self.headers: dict[str, str] = {}
        self.proxies: dict[str, str] = {}
        self.trust_env = True
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> Response:
        self.calls.append({"url": url, **kwargs})
        return Response(self.responses.pop(0))

    def close(self) -> None:
        return None


def _page(page_id: str, title: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": page_id,
        "title": title,
        "type": "page",
        "space": {"key": "DOC", "name": "Docs"},
        "version": {"when": "2026-07-31T10:00:00Z", "number": 1},
        **extra,
    }


def _connector(session: Session) -> ConfluenceRestConnector:
    source = SourceConfig(id="source-1", base_url="https://example.test", space_key="DOC")
    from alquimista.client import ConfluenceClient

    client = ConfluenceClient(source, ExtractionOptions(), session=session)
    return ConfluenceRestConnector(source, ExtractionOptions(), client=client)


def test_roots_are_remote_page_and_not_full_space_inventory() -> None:
    session = Session(
        [
            {"homepage": {"id": "homepage-1"}},
            {"results": [_page("root", "Root")], "_links": {"next": "/next"}},
            {"homepage": {"id": "homepage-1"}},
            {"results": [_page("root-2", "Root 2")], "_links": {}},
        ]
    )
    result = _connector(session).list_root_documents("DOC", limit=1)

    assert [item.id for item in result.items] == ["root", "root-2"]
    assert result.next_cursor is None
    assert len(session.calls) == 4
    assert session.calls[0]["url"].endswith("/rest/api/space/DOC")
    assert session.calls[0]["params"] == {"expand": "homepage"}
    assert session.calls[1]["url"].endswith(
        "/rest/api/content/homepage-1/child/page"
    )
    assert "cql" not in session.calls[1]["params"]
    assert session.calls[3]["params"]["start"] == 1


def test_root_pagination_starts_from_cursor_and_consumes_remaining_batches() -> None:
    session = Session(
        [
            {"homepage": {"id": "homepage-1"}},
            {"results": [_page("two", "Two")], "_links": {"next": "/next"}},
            {"homepage": {"id": "homepage-1"}},
            {"results": [_page("three", "Three")], "_links": {}},
        ]
    )
    connector = _connector(session)

    result = connector.list_root_documents(
        "DOC", cursor="1", limit=1
    )

    assert [item.id for item in result.items] == ["two", "three"]
    assert result.cursor == "1"
    assert result.next_cursor is None
    assert session.calls[3]["url"].endswith(
        "/rest/api/content/homepage-1/child/page"
    )
    assert session.calls[1]["params"]["start"] == 1
    assert session.calls[3]["params"]["start"] == 2


def test_root_without_homepage_raises_resource_not_found() -> None:
    session = Session([{"key": "DOC", "homepage": {}}])

    with pytest.raises(ResourceNotFoundError, match="homepage"):
        _connector(session).list_root_documents("DOC")

    assert len(session.calls) == 1


def test_children_query_contains_only_the_requested_parent() -> None:
    session = Session([{"results": [_page("child", "Child")], "_links": {}}])
    result = _connector(session).list_document_children("DOC", "parent-1")

    assert result.items[0].parent_id == "parent-1"
    assert "/rest/api/content/parent-1/child/page" in session.calls[0]["url"]
    assert len(session.calls) == 1


def test_children_pagination_preserves_cursor() -> None:
    session = Session(
        [
            {"results": [_page("one", "One")], "_links": {"next": "/next"}},
            {"results": [_page("two", "Two")], "_links": {}},
        ]
    )
    connector = _connector(session)
    result = connector.list_document_children("DOC", "parent-1", limit=1)

    assert [item.id for item in result.items] == ["one", "two"]
    assert result.next_cursor is None
    assert session.calls[1]["params"]["start"] == 1


def test_lazy_budget_preserves_next_cursor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("alquimista.connectors.confluence._LAZY_MAX_ITEMS", 1)
    session = Session(
        [{"results": [_page("one", "One")], "_links": {"next": "/next"}}]
    )

    result = _connector(session).list_document_children("DOC", "parent-1")

    assert [item.id for item in result.items] == ["one"]
    assert result.next_cursor == "1"
    assert len(session.calls) == 1


def test_explicit_children_and_visibility_are_preserved_unknown_is_not_inferred() -> None:
    session = Session(
        [
            {"homepage": {"id": "homepage-1"}},
            {
                "results": [
                    _page("public", "Public", public=True, hasChildren=True),
                    _page("unknown", "Unknown"),
                ],
                "_links": {},
            }
        ]
    )
    result = _connector(session).list_root_documents("DOC")

    assert result.items[0].has_children is True
    assert result.items[0].visibility is Visibility.PUBLIC
    assert result.items[1].visibility is Visibility.UNKNOWN


def test_confluence_visibility_accepts_operation_results_and_nested_restriction_lists() -> None:
    connector = _connector(Session([]))
    assert connector._explicit_visibility(
        {"restrictions": {"read": {"results": [{"operation": "read"}]}}}
    ) is Visibility.PRIVATE
    assert connector._explicit_visibility(
        {"restrictions": {"read": {"results": []}}}
    ) is Visibility.PUBLIC
    assert connector._explicit_visibility(
        {"restrictions": {"read": {"restrictions": []}}}
    ) is Visibility.PUBLIC


def test_adapter_keeps_compound_document_ids_and_does_not_store_body() -> None:
    session = Session(
        [
            {"homepage": {"id": "homepage-1"}},
            {"results": [_page("same", "Same")], "_links": {}},
        ]
    )
    connector = _connector(session)
    adapter = ConnectorDiscoveryAdapter(connector)
    document = adapter.list_root_documents(
        "DOC", cursor=None, limit=100, etag=None, token=None
    ).items[0]

    assert document.document_key == "source-1:DOC:same"
    assert "body" not in document.metadata
    assert "content" not in document.metadata


def test_unsupported_connector_reports_capability_instead_of_faking_lazy_loading() -> None:
    source = SourceConfig(id="source-2", base_url="https://example.test")

    class Legacy:
        def get_source(self) -> Any:
            return type("Source", (), {"id": source.id})()

        def list_containers(self) -> list[Any]:
            return []

    adapter = ConnectorDiscoveryAdapter(Legacy())  # type: ignore[arg-type]

    assert "list_root_documents" not in adapter.capabilities
    try:
        adapter.list_root_documents("DOC", cursor=None, limit=100, etag=None, token=None)
    except DiscoveryCapabilityError as exc:
        assert "list_root_documents" in str(exc)
    else:
        raise AssertionError("capacidade não suportada foi simulada")


def _connector_with_options(session: "Session", options: ExtractionOptions):
    from alquimista.client import ConfluenceClient

    source = SourceConfig(id="source-1", base_url="https://example.test", space_key="DOC")
    client = ConfluenceClient(source, options, session=session)
    return ConfluenceRestConnector(source, options, client=client)


def test_lazy_budget_honours_extraction_options_override() -> None:
    """Regression test for ISSUE-007: lazy_max_items must be configurable via
    ExtractionOptions instead of only the hardcoded module constants. Setting
    lazy_max_items=1 stops accumulation after one item just like the existing
    monkeypatch test, but without patching the module attribute."""
    from tests.test_lazy_confluence import Session, _page

    session = Session(
        [{"results": [_page("one", "One")], "_links": {"next": "/next"}}]
    )
    options = ExtractionOptions(lazy_max_items=1)
    result = _connector_with_options(session, options).list_document_children("DOC", "parent-1")

    assert [item.id for item in result.items] == ["one"]
    assert result.next_cursor == "1"
    assert len(session.calls) == 1


def test_lazy_batch_limit_honours_extraction_options_override() -> None:
    """Regression test for ISSUE-007: lazy_batch_limit caps each HTTP request.
    With batch_limit=1 and a response that would otherwise return 2 items, the
    request asks for at most 1 item per call, so only one arrives at a time."""
    from tests.test_lazy_confluence import Session, _page

    session = Session(
        [
            {"results": [_page("one", "One")], "_links": {"next": "/next"}},
            {"results": [_page("two", "Two")], "_links": {}},
        ]
    )
    options = ExtractionOptions(lazy_batch_limit=1)
    result = _connector_with_options(session, options).list_document_children("DOC", "parent-1", limit=1)

    assert [item.id for item in result.items] == ["one", "two"]
    # Each batch requests at most 1 item, so two responses are consumed.
    assert len(session.calls) == 2


def test_lazy_budget_defaults_preserved_when_options_are_none() -> None:
    """Regression test for ISSUE-007: when lazy_* options are None the connector
    must still use the module-level constants (existing monkeypatch tests rely
    on this fallback). This guards against accidental removal of the defaults."""
    from alquimista.connectors.confluence import _LAZY_BATCH_LIMIT, _LAZY_MAX_ITEMS

    options = ExtractionOptions()
    assert options.lazy_max_items is None
    assert options.lazy_batch_limit is None
    # The module constants still exist and define the historical defaults.
    assert _LAZY_MAX_ITEMS >= 1
    assert _LAZY_BATCH_LIMIT >= 1
