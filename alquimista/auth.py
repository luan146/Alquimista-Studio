from __future__ import annotations

import os
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .client import session_path
from .errors import AuthenticationError
from .models import SourceConfig
from .runtime import CancellationToken
from .session_store import delete_session_file, save_session


def _authenticated_identity(payload: object) -> bool:
    if not isinstance(payload, dict):
        return False
    if str(payload.get("type", "")).casefold() == "anonymous":
        return False
    identifiers = (
        payload.get("username"),
        payload.get("userKey"),
        payload.get("key"),
        payload.get("accountId"),
    )
    return any(
        str(value).strip()
        and str(value).strip().casefold() not in {"anonymous", "anonimo", "anônimo"}
        for value in identifiers
    )




def delete_session(source: SourceConfig) -> bool:
    return delete_session_file(source.id)

def _browser_session_closed(browser: object, page: object) -> bool:
    """Detect a user-closed browser/page without relying on a timeout."""
    is_connected = getattr(browser, "is_connected", None)
    if callable(is_connected):
        try:
            if not is_connected():
                return True
        except Exception:
            return True
    is_closed = getattr(page, "is_closed", None)
    if callable(is_closed):
        try:
            return bool(is_closed())
        except Exception:
            return True
    return False


def browser_login(
    source: SourceConfig,
    ready: Callable[[], None] | None = None,
    *,
    token: CancellationToken | None = None,
    timeout_seconds: float = 300,
) -> None:
    """Authenticate in a visible browser with cancellation and close detection."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise AuthenticationError(
            "O suporte ao navegador não está instalado. Execute tools\\install\\instalar_navegador.bat."
        ) from exc
    if timeout_seconds <= 0:
        raise AuthenticationError("O tempo limite do login deve ser positivo.")
    cancellation = token or CancellationToken()
    destination = session_path(source.id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    browser: Any | None = None
    with sync_playwright() as playwright:
        try:
            try:
                browser = playwright.chromium.launch(headless=False, channel="chrome")
            except Exception:
                browser = playwright.chromium.launch(headless=False)
        except Exception as exc:
            raise AuthenticationError(
                "Não foi possível abrir o navegador. Instale o Chromium do Playwright."
            ) from exc
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(source.base_url, wait_until="domcontentloaded")
            if _browser_session_closed(browser, page):
                raise AuthenticationError(
                    "O navegador foi fechado antes da autenticação ser concluída."
                )
            if ready:
                ready()
            deadline = time.monotonic() + timeout_seconds
            current_user_url = f"{source.base_url.rstrip('/')}/rest/api/user/current"
            while True:
                cancellation.check()
                if _browser_session_closed(browser, page):
                    raise AuthenticationError(
                        "O navegador foi fechado antes da autenticação ser concluída."
                    )
                try:
                    response = context.request.get(
                        current_user_url,
                        timeout=10_000,
                        fail_on_status_code=False,
                    )
                    if response.status == 200 and _authenticated_identity(response.json()):
                        break
                except Exception:
                    if _browser_session_closed(browser, page):
                        raise AuthenticationError(
                            "O navegador foi fechado antes da autenticação ser concluída."
                        ) from None
                    # SSO redirects can make the probe fail while the user is logging in.
                if time.monotonic() >= deadline:
                    raise AuthenticationError(
                        "O login não foi confirmado dentro do tempo limite. "
                        "A sessão anterior foi preservada."
                    )
                cancellation.wait(min(1.0, max(0.0, deadline - time.monotonic())))
            fd, temporary = tempfile.mkstemp(
                prefix=f".{destination.name}.",
                suffix=".pending",
                dir=destination.parent,
            )
            os.close(fd)
            context.storage_state(path=temporary)
            import json

            state = json.loads(Path(temporary).read_text(encoding="utf-8"))
            save_session(source.id, state)
            Path(temporary).unlink(missing_ok=True)
            temporary = None
        finally:
            if temporary:
                try:
                    Path(temporary).unlink(missing_ok=True)
                except OSError:
                    pass
            try:
                browser.close()
            except Exception:
                pass
