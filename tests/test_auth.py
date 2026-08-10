from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from alquimista.auth import browser_login, delete_session
from alquimista.client import session_path
from alquimista.errors import AuthenticationError
from alquimista.models import SourceConfig


class FakeResponse:
    def __init__(self, payload: dict[str, Any], status: int = 200) -> None:
        self.payload = payload
        self.status = status

    def json(self) -> dict[str, Any]:
        return self.payload


def install_fake_playwright(
    monkeypatch: pytest.MonkeyPatch,
    identities: list[dict[str, Any]],
    events: list[str],
) -> None:
    class Request:
        def get(self, *_args: Any, **_kwargs: Any) -> FakeResponse:
            events.append("probe")
            payload = identities.pop(0) if len(identities) > 1 else identities[0]
            return FakeResponse(payload)

    class Page:
        def goto(self, *_args: Any, **_kwargs: Any) -> None:
            events.append("goto")

    class Context:
        request = Request()

        def new_page(self) -> Page:
            return Page()

        def storage_state(self, *, path: str) -> None:
            events.append("storage_state")
            Path(path).write_text(json.dumps({"cookies": []}), encoding="utf-8")

    class Browser:
        def new_context(self) -> Context:
            return Context()

        def close(self) -> None:
            events.append("close")

    class Chromium:
        def launch(self, **_kwargs: Any) -> Browser:
            events.append("launch")
            return Browser()

    class Playwright:
        chromium = Chromium()

    class Manager:
        def __enter__(self) -> Playwright:
            return Playwright()

        def __exit__(self, *_args: Any) -> None:
            return None

    module = types.ModuleType("playwright.sync_api")
    module.sync_playwright = lambda: Manager()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "playwright.sync_api", module)


def test_browser_login_waits_for_authenticated_identity_and_saves_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    events: list[str] = []
    install_fake_playwright(
        monkeypatch,
        [{"type": "anonymous"}, {"username": "analista"}],
        events,
    )
    source = SourceConfig(id="safe_source", base_url="https://example.test")

    browser_login(source, timeout_seconds=2)

    assert events.index("probe") < events.index("storage_state")
    assert events.count("probe") == 2
    assert session_path(source.id).is_file()
    assert not list(session_path(source.id).parent.glob("*.pending"))


def test_browser_login_timeout_preserves_previous_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    events: list[str] = []
    install_fake_playwright(monkeypatch, [{"type": "anonymous"}], events)
    source = SourceConfig(id="safe_source", base_url="https://example.test")
    destination = session_path(source.id)
    destination.parent.mkdir(parents=True)
    destination.write_text("previous", encoding="utf-8")

    with pytest.raises(AuthenticationError, match="tempo limite"):
        browser_login(source, timeout_seconds=0.01)

    assert destination.read_text(encoding="utf-8") == "previous"
    assert "storage_state" not in events


def test_session_path_rejects_traversal_and_legitimate_delete_still_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    with pytest.raises(AuthenticationError):
        session_path(r"..\victim")

    source = SourceConfig(id="source_01")
    path = session_path(source.id)
    path.parent.mkdir(parents=True)
    path.write_text("{}", encoding="utf-8")
    assert delete_session(source)
    assert not path.exists()
