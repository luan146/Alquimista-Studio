"""Credentials must only be sent to the configured origin (R-09)."""
from __future__ import annotations

from typing import Any

import requests
from requests.adapters import BaseAdapter

from alquimista.client import ConfluenceClient
from alquimista.connectors.http import ApiHttpClient
from alquimista.models import AuthMode, ExtractionOptions, SourceConfig


class _RecordingAdapter(BaseAdapter):
    """Answers every request with JSON and records the headers actually sent."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: dict[str, dict[str, str]] = {}

    def send(self, request: requests.PreparedRequest, **_kwargs: Any) -> requests.Response:
        self.sent[str(request.url)] = dict(request.headers)
        response = requests.Response()
        response.status_code = 200
        response._content = b"{}"
        response.headers["Content-Type"] = "application/json"
        response.url = str(request.url)
        response.request = request
        return response

    def close(self) -> None:
        pass


def _session() -> tuple[requests.Session, _RecordingAdapter]:
    session = requests.Session()
    adapter = _RecordingAdapter()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session, adapter


def test_api_client_sends_credentials_only_to_its_origin() -> None:
    session, adapter = _session()
    client = ApiHttpClient(
        "https://api.example.com/v1",
        ExtractionOptions(),
        session=session,
        headers={"Authorization": "Bearer secret", "api_token": "secret2"},
    )

    client.get_json("/items")
    client.get_json("https://api.example.com/v1/next")
    client.download("https://cdn.other.com/file.pdf")
    client.download("http://api.example.com/v1/file.pdf")  # same host, downgraded to HTTP

    assert adapter.sent["https://api.example.com/v1/items"]["Authorization"] == "Bearer secret"
    assert adapter.sent["https://api.example.com/v1/next"]["api_token"] == "secret2"
    for url in ("https://cdn.other.com/file.pdf", "http://api.example.com/v1/file.pdf"):
        assert "Authorization" not in adapter.sent[url]
        assert "api_token" not in adapter.sent[url]
        assert adapter.sent[url]["User-Agent"].startswith("ALQuimista")


def _confluence(mode: AuthMode, session: requests.Session) -> ConfluenceClient:
    source = SourceConfig(
        id="c1", base_url="https://wiki.example.com", auth_mode=mode, username="ana@example.com", space_key="DOC"
    )
    return ConfluenceClient(source, ExtractionOptions(), secret="secret", session=session)


def test_confluence_client_keeps_basic_and_bearer_auth_on_its_origin() -> None:
    for mode in (AuthMode.BASIC, AuthMode.BEARER):
        session, adapter = _session()
        client = _confluence(mode, session)

        client._request("/rest/api/space")
        client._request("https://evil.example.net/steal")

        assert "Authorization" in adapter.sent["https://wiki.example.com/rest/api/space"]
        assert "Authorization" not in adapter.sent["https://evil.example.net/steal"]
