from __future__ import annotations

from typing import Any

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from alquimista.errors import (
    AlquimistaError,
    ApiConnectionError,
    ApiRateLimitError,
    AuthenticationError,
    ConfluenceConnectionError,
    ConnectorError,
    InvalidResponseError,
    PermissionDeniedError,
    RateLimitError,
    ResourceNotFoundError,
)
from alquimista.ui.operation_controller import _connection_error_presentation
from alquimista.ui.workers import Worker


@pytest.fixture(autouse=True)
def _isolated_pt_br_language(qapp: QApplication):
    previous = qapp.property("_alquimista_language")
    qapp.setProperty("_alquimista_language", "pt-BR")
    try:
        yield
    finally:
        qapp.setProperty("_alquimista_language", previous)


@pytest.mark.parametrize(
    "error_type",
    [
        AuthenticationError,
        PermissionDeniedError,
        ResourceNotFoundError,
        ApiConnectionError,
        ApiRateLimitError,
        InvalidResponseError,
    ],
)
def test_connector_errors_share_neutral_base(error_type: type[Exception]) -> None:
    error = error_type("falha")

    assert isinstance(error, ConnectorError)
    assert isinstance(error, AlquimistaError)


def test_confluence_error_names_are_compatibility_aliases() -> None:
    assert ConfluenceConnectionError is ApiConnectionError
    assert RateLimitError is ApiRateLimitError
    assert isinstance(InvalidResponseError("inválida"), ConfluenceConnectionError)


def test_worker_preserves_exception_instance_in_failure_signal() -> None:
    received: list[tuple[object, str]] = []

    def fail(*_args: Any) -> None:
        raise AuthenticationError("token recusado")

    worker = Worker(fail)
    worker.signals.failed.connect(lambda error, detail: received.append((error, detail)))

    worker.run()

    assert len(received) == 1
    error, detail = received[0]
    assert isinstance(error, AuthenticationError)
    assert str(error) == "token recusado"
    assert "AuthenticationError" in detail


def test_worker_delivers_exception_through_queued_thread_signal(qtbot) -> None:
    def fail(*_args: Any) -> None:
        raise PermissionDeniedError("acesso negado")

    worker = Worker(fail)
    pool = QThreadPool()
    with qtbot.waitSignal(worker.signals.failed, timeout=3000) as blocker:
        pool.start(worker)

    error, detail = blocker.args
    assert isinstance(error, PermissionDeniedError)
    assert str(error) == "acesso negado"
    assert "PermissionDeniedError" in detail
    assert pool.waitForDone(3000)


@pytest.mark.parametrize(
    ("error", "state_fragment", "title_fragment"),
    [
        (AuthenticationError("recusado"), "autenticação", "entrar"),
        (PermissionDeniedError("negado"), "Acesso restrito", "permissão"),
        (ResourceNotFoundError("ausente"), "não encontrado", "não encontrado"),
        (ApiRateLimitError("429"), "GitBook", "Limite"),
        (InvalidResponseError("JSON"), "GitBook", "Resposta inválida"),
        (ApiConnectionError("offline"), "GitBook", "GitBook"),
    ],
)
def test_typed_connection_errors_have_specific_presentation(
    error: Exception,
    state_fragment: str,
    title_fragment: str,
) -> None:
    state, title = _connection_error_presentation(error, "GitBook")

    assert state_fragment.casefold() in state.casefold()
    assert title_fragment.casefold() in title.casefold()


def test_connection_error_presentation_accepts_legacy_string() -> None:
    state, title = _connection_error_presentation(
        "Autenticação recusada (HTTP 401)",
        "Zendesk",
    )

    assert "autenticação" in state.casefold()
    assert "entrar" in title.casefold()
