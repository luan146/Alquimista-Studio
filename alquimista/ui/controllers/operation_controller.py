from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QMessageBox

from ...errors import (
    ApiConnectionError,
    ApiRateLimitError,
    AuthenticationError,
    InvalidResponseError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from ...runtime import CancellationToken
from ..i18n import translate_text
from ..workers import Worker

WorkerFunction = Callable[..., Any]
DoneCallback = Callable[[Any], None]


def _connection_error_presentation(
    error: Exception | str,
    integration_name: str,
) -> tuple[str, str]:
    """Return a user-facing connection state and title for a typed failure."""
    message = str(error)
    lowered = message.casefold()
    if isinstance(error, AuthenticationError) or (
        isinstance(error, str)
        and ("401" in message or "autentica" in lowered or "sessão expirada" in lowered)
    ):
        return (
            translate_text(
                "Falha de autenticação — credenciais inválidas ou sessão expirada"
            ),
            translate_text("Não foi possível entrar"),
        )
    if isinstance(error, PermissionDeniedError) or (
        isinstance(error, str)
        and ("403" in message or "permiss" in lowered or "restrito" in lowered)
    ):
        return (
            translate_text(
                "Acesso restrito — a conta não possui permissão para este conteúdo"
            ),
            translate_text("Página sem permissão"),
        )
    if isinstance(error, ResourceNotFoundError):
        return (
            translate_text(
                "Recurso não encontrado — verifique a fonte e o conteúdo selecionado"
            ),
            translate_text("Conteúdo não encontrado"),
        )
    if isinstance(error, ApiRateLimitError):
        return (
            translate_text(
                "Limite de requisições atingido em {name} — aguarde e tente novamente"
            ).format(name=integration_name),
            translate_text("Limite de requisições"),
        )
    if isinstance(error, InvalidResponseError):
        return (
            translate_text(
                "Resposta inválida recebida de {name} — tente novamente mais tarde"
            ).format(name=integration_name),
            translate_text("Resposta inválida"),
        )
    if isinstance(error, ApiConnectionError):
        return (
            translate_text(
                "Falha de comunicação — {name} está indisponível ou inacessível"
            ).format(name=integration_name),
            translate_text("{name} indisponível").format(name=integration_name),
        )
    return (
        translate_text(
            "Não foi possível validar a conexão com {name}"
        ).format(name=integration_name),
        translate_text("Falha na conexão"),
    )


class WorkerOperationController:
    """Own the lifecycle of the worker used by the main operation flow."""

    def __init__(
        self, window: Any, thread_pool: QThreadPool | None = None
    ) -> None:
        self.window = window
        self.thread_pool = thread_pool or QThreadPool.globalInstance()

    @property
    def worker(self) -> Worker | None:
        return self.window.worker

    @worker.setter
    def worker(self, value: Worker | None) -> None:
        self.window.worker = value

    @property
    def token(self) -> CancellationToken | None:
        return self.window.token

    @token.setter
    def token(self, value: CancellationToken | None) -> None:
        self.window.token = value

    def _set_state(self, value: str) -> None:
        view_state = getattr(self.window, "view_state", None)
        if view_state is not None:
            view_state.operation_status = value
        self.window.operation_status = value

    def start(self, function: WorkerFunction, done: DoneCallback) -> None:
        window = self.window
        if self.worker is not None:
            QMessageBox.information(
                window,
                translate_text("Operação em andamento"),
                translate_text("Aguarde ou cancele a operação atual."),
            )
            return

        self._set_state("STARTING")
        self.token = CancellationToken()
        worker = Worker(function, token=self.token)
        self.worker = worker
        window.started_at = time.monotonic()
        window.cancel_button.setEnabled(True)
        window.progress.setValue(0)
        worker.signals.progress.connect(self.on_progress)
        worker.signals.log.connect(self.append_log)
        worker.signals.failed.connect(self.worker_failed)
        worker.signals.succeeded.connect(done)
        worker.signals.finished.connect(self.worker_finished)
        self.thread_pool.start(worker)
        self._set_state("RUNNING")
        window._refresh_dashboard()
        if hasattr(window, "_update_consolidation_action_availability"):
            window._update_consolidation_action_availability()

    def on_progress(self, done: int, total: int, item: str) -> None:
        window = self.window
        percent = int(done * 100 / total) if total else 0
        window.progress.setValue(percent)
        elapsed = time.monotonic() - window.started_at
        window.progress_label.setText(
            translate_text("{done}/{total}  —  {item}  —  {elapsed:.1f}s decorridos").format(
                done=done, total=total, item=item, elapsed=elapsed
            )
        )
        if getattr(window, "_tree_loading", False) and hasattr(
            window, "tree_load_progress"
        ):
            if total > 0:
                window.tree_load_progress.setRange(0, 100)
                window.tree_load_progress.setValue(max(0, min(100, percent)))
                progress_text = f"{done}/{total}"
            else:
                window.tree_load_progress.setRange(0, 0)
                progress_text = translate_text("em andamento")
            if item:
                window._tree_loading_message = translate_text(
                    "Carregando ({progress}): {item}"
                ).format(progress=progress_text, item=item)
                window.tree_load_status.setText(window._tree_loading_message)
                for status_name in ("page_render_status", "selection_render_status"):
                    status = getattr(window, status_name, None)
                    if status is not None:
                        status.setText(window._tree_loading_message)

    def append_log(self, message: str) -> None:
        window = self.window
        window.technical_logger.info(message)
        if hasattr(window, "log_text"):
            window.log_text.append(f"[{time.strftime('%H:%M:%S')}] {message}")

    def worker_failed(self, error: Exception | str, detail: str) -> None:
        window = self.window
        message = str(error)
        self.append_log(f"{translate_text('FALHA')}: {message}")
        if detail.strip():
            self.append_log(f"{translate_text('Detalhes técnicos')}:\n{detail.rstrip()}")
        lowered = f"{message}\n{detail}".casefold()
        cancelled = bool(self.token and self.token.cancelled) or "cancel" in lowered
        self._set_state("CANCELLED" if cancelled else "FAILED")
        if cancelled:
            if getattr(window, "_tree_loading", False):
                window._set_tree_loading(False, translate_text("Carregamento cancelado."))
            if hasattr(window, "progress_label"):
                window.progress_label.setText(translate_text("Operação cancelada."))
            window.statusBar().showMessage(translate_text("Operação cancelada."), 5000)
            return

        if (
            hasattr(window, "connection_state")
            and window.stack.currentWidget() is window.pages.get("connection")
        ):
            source = window.source_by_combo(window.connection_source)
            integration_name = translate_text("a integração")
            if source:
                registry = getattr(window, "connector_registry", None)
                try:
                    descriptor = registry.get(source.source_type) if registry else None
                except (KeyError, ValueError):
                    descriptor = None
                integration_name = str(
                    getattr(descriptor, "display_name", "")
                    or getattr(descriptor, "integration_name", "")
                    or getattr(source, "name", "")
                    or integration_name
                )
            state, title = _connection_error_presentation(error, integration_name)
            window.connection_state.setText(state)
            if source:
                window.connection_states[source.id] = state
            QMessageBox.critical(window, title, f"{state}\n\n{message}")
            return

        QMessageBox.critical(window, translate_text("Operação não concluída"), message)

    def worker_finished(self) -> None:
        window = self.window
        if getattr(window, "operation_status", "") == "RUNNING":
            self._set_state("SUCCEEDED")
        self.worker = None
        self.token = None
        if getattr(window, "_tree_loading", False):
            window._set_tree_loading(False)
        window.cancel_button.setEnabled(False)
        window._refresh_dashboard()
        if hasattr(window, "_update_consolidation_action_availability"):
            window._update_consolidation_action_availability()
        self._set_state("IDLE")

    def cancel(self, *, confirm: bool = True) -> None:
        window = self.window
        if not self.token:
            return
        if confirm and (
            QMessageBox.question(
                window,
                translate_text("Cancelar operação"),
                translate_text(
                    "Deseja interromper a operação atual? Arquivos concluídos serão preservados."
                ),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.token.cancel()
        self._set_state("CANCELLED")
        if hasattr(window, "progress_label"):
            window.progress_label.setText(
                translate_text("Cancelamento solicitado. Finalizando a etapa atual…")
            )


OperationController = WorkerOperationController

__all__ = [
    "DoneCallback",
    "OperationController",
    "WorkerFunction",
    "WorkerOperationController",
    "_connection_error_presentation",
]
