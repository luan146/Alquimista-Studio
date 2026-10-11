"""Connectors must surface API failures and read every page of a listing."""
from __future__ import annotations

from typing import Any

import pytest

from alquimista.connectors.helpscout import HelpScoutConnector
from alquimista.connectors.outline import OutlineConnector
from alquimista.errors import AuthenticationError
from alquimista.models import ExtractionOptions, SourceConfig


class _Response:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FailingClient:
    def get(self, *_args: Any, **_kwargs: Any) -> Any:
        raise AuthenticationError("token inválido")

    post = get

    def close(self) -> None:
        pass


def _outline(client: Any) -> OutlineConnector:
    source = SourceConfig(id="o", name="O", source_type="outline_api", base_url="https://app.getoutline.com/api")
    return OutlineConnector(source, ExtractionOptions.model_validate({}), secret="x", client=client)


def _helpscout(client: Any) -> HelpScoutConnector:
    source = SourceConfig(id="h", name="H", source_type="helpscout_docs", base_url="https://docsapi.helpscout.net/v1")
    return HelpScoutConnector(source, ExtractionOptions.model_validate({}), secret="x", client=client)


def test_listing_failures_are_raised_not_hidden_behind_fake_containers() -> None:
    for connector in (_outline(_FailingClient()), _helpscout(_FailingClient())):
        with pytest.raises(AuthenticationError):
            connector.list_containers()
        with pytest.raises(AuthenticationError):
            connector.list_documents("col-a")


def test_outline_documents_are_paginated() -> None:
    class Client(_FailingClient):
        def post(self, path: str, *, json: dict[str, Any]) -> _Response:
            assert path == "/documents.list"
            total, offset = 230, json["offset"]
            ids = range(offset, min(offset + json["limit"], total))
            return _Response({"data": [{"id": f"d{i}", "title": f"Doc {i}"} for i in ids]})

    assert len(_outline(Client()).list_documents("col-a")) == 230


def test_helpscout_articles_are_paginated() -> None:
    class Client(_FailingClient):
        def get(self, path: str, **_kwargs: Any) -> _Response:
            page = int(path.split("page=")[1].split("&")[0])
            items = [{"id": f"a{page}-{i}", "name": f"Artigo {i}"} for i in range(50 if page < 3 else 7)]
            return _Response({"articles": {"items": items, "pages": 3}})

    assert len(_helpscout(Client()).list_documents("col-a")) == 107
