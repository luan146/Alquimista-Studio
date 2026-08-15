from __future__ import annotations

import base64
import ctypes
import json
import os
import sys
from ctypes import wintypes
from pathlib import Path
from typing import Any

from .errors import AuthenticationError
from .models import validate_source_identifier
from .storage import atomic_write_text

_FORMAT = "alquimista-session"
_ENTROPY = b"ALQuimista Studio browser session v1"


def session_directory() -> Path:
    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "ALQuimista Studio" / "sessions"
    return Path.home() / ".local" / "share" / "alquimista-studio" / "sessions"


def session_path(source_id: str) -> Path:
    try:
        safe_id = validate_source_identifier(source_id)
    except ValueError as exc:
        raise AuthenticationError("O identificador da fonte é inseguro.") from exc
    directory = session_directory().resolve()
    candidate = (directory / f"{safe_id}.session.json").resolve()
    if candidate.parent != directory:
        raise AuthenticationError("O caminho da sessão sai da pasta permitida.")
    return candidate


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes) -> tuple[_DataBlob, Any]:
    buffer = ctypes.create_string_buffer(data)
    blob = _DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    return blob, buffer


def _crypt_protect(data: bytes) -> bytes:
    if sys.platform != "win32":
        return data
    source, source_buffer = _blob(data)
    entropy, entropy_buffer = _blob(_ENTROPY)
    output = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(source), "ALQuimista Studio", ctypes.byref(entropy),
        None, None, 0, ctypes.byref(output),
    ):
        raise ctypes.WinError()
    del source_buffer, entropy_buffer
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def _crypt_unprotect(data: bytes) -> bytes:
    if sys.platform != "win32":
        return data
    source, source_buffer = _blob(data)
    entropy, entropy_buffer = _blob(_ENTROPY)
    output = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(source), None, ctypes.byref(entropy),
        None, None, 0, ctypes.byref(output),
    ):
        raise ctypes.WinError()
    del source_buffer, entropy_buffer
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(output.pbData)


def save_session(source_id: str, state: dict[str, Any]) -> Path:
    path = session_path(source_id)
    raw = json.dumps(state, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    protection = "dpapi-current-user" if sys.platform == "win32" else "file-permissions"
    try:
        protected = _crypt_protect(raw)
    except OSError:
        # Some test and managed Windows environments expose win32 without a
        # usable crypt32 provider. Keep the atomic session contract and rely
        # on the restrictive file mode in that fallback case.
        protected = raw
        protection = "file-permissions"
    document = {
        "format": _FORMAT,
        "version": 1,
        "protection": protection,
        "payload": base64.b64encode(protected).decode("ascii"),
    }
    atomic_write_text(path, json.dumps(document, ensure_ascii=False) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def load_session(source_id: str, *, legacy_path: Path | None = None) -> dict[str, Any]:
    path = session_path(source_id)
    selected = path if path.exists() else legacy_path
    if selected is None or not selected.exists():
        raise AuthenticationError("A sessão do navegador não existe. Use Fazer login.")
    try:
        document = json.loads(selected.read_text(encoding="utf-8"))
        encrypted = isinstance(document, dict) and document.get("format") == _FORMAT
        if encrypted:
            protected = base64.b64decode(document["payload"], validate=True)
            if document.get("protection") == "file-permissions":
                state = json.loads(protected.decode("utf-8"))
            else:
                state = json.loads(_crypt_unprotect(protected).decode("utf-8"))
        else:
            state = document
        if not isinstance(state, dict) or not isinstance(state.get("cookies", []), list):
            raise ValueError("estrutura de sessão inválida")
    except Exception as exc:
        raise AuthenticationError(
            "A sessão salva está inválida ou pertence a outro usuário do Windows."
        ) from exc
    if selected != path or not encrypted:
        save_session(source_id, state)
    return state


def session_exists(source_id: str) -> bool:
    return session_path(source_id).exists()


def delete_session_file(source_id: str) -> bool:
    path = session_path(source_id)
    if not path.exists():
        return False
    path.unlink(missing_ok=True)
    return True
