from __future__ import annotations

from typing import Any

import pytest
import requests

from alquimista.client import ConfluenceClient
from alquimista.errors import (
    AuthenticationError,
    ConfluenceConnectionError,
    InvalidResponseError,
    PermissionDeniedError,
    RateLimitError,
    ResourceNotFoundError,
)
from alquimista.models import ExtractionOptions, SourceConfig


class Response:
    def __init__(
        self,
        status: int = 200,
        payload: Any = None,
        *,
        headers: dict[str, str] | None = None,
        invalid_json: bool = False,
    ) -> None:
        self.status_code = status
        self.payload = payload if payload is not None else {}
        self.headers = headers or {}
        self.text = ""
        self.invalid_json = invalid_json

    def json(self) -> Any:
        if self.invalid_json:
            raise ValueError("bad")
        return self.payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code))


class Session:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = list(responses)
        self.headers: dict[str, str] = {}
        self.proxies: dict[str, str] = {}
        self.cookies = requests.cookies.RequestsCookieJar()
        self.trust_env = True
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> Response:
        self.calls.append({"url": url, **kwargs})
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    def close(self) -> None:
        pass


def source() -> SourceConfig:
    return SourceConfig(
        id="s1",
        name="Fonte",
        base_url="https://example.test",
        space_key="DOC",
        root_mode="id",
        root_value="100",
    )


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, ResourceNotFoundError),
    ],
)
def test_http_errors_are_specific(status: int, error: type[Exception]) -> None:
    client = ConfluenceClient(
        source(), ExtractionOptions(retry_count=1), session=Session([Response(status)])
    )
    with pytest.raises(error):
        client.test_connection()


def test_429_respects_retry_after() -> None:
    delays: list[float] = []
    client = ConfluenceClient(
        source(),
        ExtractionOptions(retry_count=2),
        session=Session(
            [
                Response(429, headers={"Retry-After": "0"}),
                Response(200, {"size": 1, "results": [{}]}),
            ]
        ),
    )
    client.token.wait = lambda seconds: delays.append(seconds)  # type: ignore[method-assign]
    assert client.test_connection()["spaces_visible"] == 1
    assert 0.0 in delays


def test_terminal_429_is_rate_limit_error() -> None:
    client = ConfluenceClient(
        source(), ExtractionOptions(retry_count=1), session=Session([Response(429)])
    )
    with pytest.raises(RateLimitError):
        client.test_connection()


def test_invalid_json_is_reported() -> None:
    client = ConfluenceClient(
        source(),
        ExtractionOptions(retry_count=1),
        session=Session([Response(200, invalid_json=True)]),
    )
    with pytest.raises(InvalidResponseError):
        client.test_connection()


def test_pagination_and_deduplication() -> None:
    session = Session(
        [
            Response(
                200,
                {
                    "results": [{"id": "1"}, {"id": "1"}],
                    "_links": {"next": "/next"},
                },
            ),
            Response(200, {"results": [{"id": "2"}], "_links": {}}),
        ]
    )
    client = ConfluenceClient(source(), ExtractionOptions(), session=session)
    pages = client.list_pages()
    assert [page["id"] for page in pages] == ["1", "2"]
    assert len(session.calls) == 2


def test_list_descendant_pages_paginates_and_preserves_provider_order() -> None:
    session = Session(
        [
            Response(
                200,
                {
                    "results": [{"id": "child-1"}, {"id": "child-2"}],
                    "_links": {"next": "/next"},
                },
            ),
            Response(200, {"results": [{"id": "child-3"}], "_links": {}}),
        ]
    )
    client = ConfluenceClient(source(), ExtractionOptions(), session=session)

    pages = client.list_descendant_pages("root-1")

    assert [page["id"] for page in pages] == ["child-1", "child-2", "child-3"]
    assert len(session.calls) == 2
    assert session.calls[0]["params"]["cql"] == "ancestor=root-1 AND type=page"
    assert session.calls[1]["params"]["start"] == 2


def test_list_pages_enriches_restrictions_when_listing_only_exposes_expandable_link() -> None:
    session = Session(
        [
            Response(
                200,
                {
                    "results": [
                        {
                            "id": "42",
                            "title": "Restrita",
                            "_expandable": {"restrictions": "/rest/api/content/42/restriction"},
                        }
                    ],
                    "_links": {},
                },
            ),
            Response(
                200,
                {
                    "results": [
                        {"operation": "read", "restrictions": {"user": {"results": [{"id": "u1"}]}}}
                    ],
                    "_links": {},
                },
            ),
        ]
    )
    authenticated = source().model_copy(update={"auth_mode": "basic"})
    page = ConfluenceClient(authenticated, ExtractionOptions(), secret="password", session=session).list_pages()[0]
    assert page["restrictions"]["read"]["results"][0]["operation"] == "read"
    assert session.calls[1]["url"].endswith("/rest/api/content/42/restriction/byOperation/read")


def test_authenticated_list_pages_checks_restrictions_without_expandable_metadata() -> None:
    session = Session(
        [
            Response(200, {"results": [{"id": "43", "title": "Restrita"}], "_links": {}}),
            Response(200, {"results": []}),
        ]
    )
    authenticated = source().model_copy(update={"auth_mode": "basic"})
    page = ConfluenceClient(authenticated, ExtractionOptions(), secret="password", session=session).list_pages()[0]
    assert page["restrictions"]["read"]["results"] == []
    assert session.calls[1]["url"].endswith("/rest/api/content/43/restriction/byOperation/read")


def test_entire_space_tree_uses_homepage_and_all_space_pages() -> None:
    configured = source().model_copy(
        update={"root_mode": "space", "root_value": "", "space_key": "DOC"}
    )
    session = Session(
        [
            Response(200, {"homepage": {"id": "100"}}),
            Response(200, {"id": "100", "title": "Home", "space": {"key": "DOC"}}),
            Response(
                200,
                {
                    "results": [
                        {"id": "100", "title": "Home"},
                        {"id": "200", "title": "Independent page"},
                    ],
                    "_links": {},
                },
            ),
        ]
    )

    root, pages = ConfluenceClient(
        configured, ExtractionOptions(), session=session
    ).fetch_tree()

    assert root["id"] == "100"
    assert {page["id"] for page in pages} == {"100", "200"}
    assert session.calls[0]["url"].endswith("/rest/api/space/DOC")
    assert 'space="DOC"' in session.calls[2]["params"]["cql"]


def test_client_defense_in_depth_rejects_authenticated_http() -> None:
    unsafe = SourceConfig.model_construct(
        id="s1",
        name="Fonte",
        base_url="http://intranet.example",
        auth_mode="bearer",
    )
    with pytest.raises(AuthenticationError, match="HTTPS"):
        ConfluenceClient(
            unsafe,
            ExtractionOptions(),
            secret="temporary-secret",
            session=Session([]),
        )



def test_terminal_500_message_includes_url_and_attempts() -> None:
    client = ConfluenceClient(
        source(), ExtractionOptions(retry_count=1), session=Session([Response(500)])
    )
    with pytest.raises(ConfluenceConnectionError) as exc_info:
        client.test_connection()
    message = str(exc_info.value)
    assert "HTTP 500" in message
    assert "https://example.test/rest/api/space" in message
    assert "1 tentativa" in message


def test_missing_confluence_base_url_fails_before_requests() -> None:
    client = ConfluenceClient(
        SourceConfig(id="s1", name="Fonte sem URL"),
        ExtractionOptions(retry_count=1),
        session=Session([]),
    )
    with pytest.raises(ConfluenceConnectionError, match="base_url.*vazia"):
        client.test_connection()


def test_terminal_502_message_includes_url() -> None:
    client = ConfluenceClient(
        source(), ExtractionOptions(retry_count=1), session=Session([Response(502)])
    )
    with pytest.raises(ConfluenceConnectionError) as exc_info:
        client.test_connection()
    assert "HTTP 502" in str(exc_info.value)
    assert "https://example.test/rest/api/space" in str(exc_info.value)


def test_exponential_backoff_without_retry_after() -> None:
    delays: list[float] = []
    client = ConfluenceClient(
        source(),
        ExtractionOptions(retry_count=3),
        session=Session(
            [Response(500), Response(500), Response(200, {"size": 1})]
        ),
    )
    client.token.wait = lambda seconds: delays.append(seconds)  # type: ignore[method-assign]
    client._random = lambda: 0.0  # type: ignore[method-assign]
    client.rate_limiter.wait = lambda: None  # type: ignore[method-assign]
    assert client.test_connection()["spaces_visible"] == 1
    assert len(delays) == 2
    assert delays[0] == pytest.approx(1.0)
    assert delays[1] == pytest.approx(2.0)


def test_429_message_includes_url() -> None:
    client = ConfluenceClient(
        source(), ExtractionOptions(retry_count=1), session=Session([Response(429)])
    )
    with pytest.raises(RateLimitError) as exc_info:
        client.test_connection()
    assert "HTTP 429" in str(exc_info.value)
    assert "https://example.test/rest/api/space" in str(exc_info.value)
