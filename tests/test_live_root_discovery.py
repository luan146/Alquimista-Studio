from __future__ import annotations

import os

import pytest

from alquimista.client import ConfluenceClient
from alquimista.models import ExtractionOptions, SourceConfig


@pytest.mark.skipif(
    os.getenv("ALQUIMISTA_LIVE_TESTS") != "1"
    or not os.getenv("ALQUIMISTA_LIVE_BASE_URL")
    or not os.getenv("ALQUIMISTA_LIVE_SPACE_KEY"),
    reason=(
        "teste live desabilitado; defina ALQUIMISTA_LIVE_TESTS=1, "
        "ALQUIMISTA_LIVE_BASE_URL e ALQUIMISTA_LIVE_SPACE_KEY para habilitar"
    ),
)
def test_live_public_space_returns_root_children() -> None:
    base_url = os.environ["ALQUIMISTA_LIVE_BASE_URL"]
    space_key = os.environ["ALQUIMISTA_LIVE_SPACE_KEY"]
    source = SourceConfig(
        id="live-test",
        name="Fonte live",
        base_url=base_url,
        space_key=space_key,
    )
    options = ExtractionOptions(
        retry_count=1,
        connect_timeout_seconds=15,
        timeout_seconds=60,
    )

    with ConfluenceClient(source, options) as client:
        page = client.list_root_pages(limit=5)

    assert page["results"], "o espaco publico deveria possuir uma primeira camada"
