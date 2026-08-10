from __future__ import annotations

import json
from pathlib import Path

import pytest

from alquimista import session_store


def test_session_is_wrapped_and_round_trips_without_plaintext_cookie(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(session_store, "_crypt_protect", lambda data: b"protected:" + data)
    monkeypatch.setattr(
        session_store,
        "_crypt_unprotect",
        lambda data: data.removeprefix(b"protected:"),
    )
    state = {"cookies": [{"name": "session", "value": "highly-secret-cookie"}]}

    path = session_store.save_session("source_01", state)

    stored = path.read_text(encoding="utf-8")
    assert "highly-secret-cookie" not in stored
    assert json.loads(stored)["format"] == "alquimista-session"
    assert session_store.load_session("source_01") == state


def test_plaintext_legacy_session_is_migrated_on_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(session_store, "_crypt_protect", lambda data: b"protected:" + data)
    monkeypatch.setattr(
        session_store,
        "_crypt_unprotect",
        lambda data: data.removeprefix(b"protected:"),
    )
    path = session_store.session_path("source_01")
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"cookies": [{"name": "sid", "value": "legacy-secret"}]}),
        encoding="utf-8",
    )

    state = session_store.load_session("source_01")

    assert state["cookies"][0]["value"] == "legacy-secret"
    migrated = path.read_text(encoding="utf-8")
    assert "legacy-secret" not in migrated
    assert json.loads(migrated)["format"] == "alquimista-session"


def test_invalid_session_has_safe_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    path = session_store.session_path("source_01")
    path.parent.mkdir(parents=True)
    path.write_text("not-json", encoding="utf-8")

    with pytest.raises(Exception, match="inválida"):
        session_store.load_session("source_01")
