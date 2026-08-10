from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QMessageBox

from ..runtime import CancellationToken
from .workers import Worker

WorkerFunction = Callable[..., Any]
DoneCallback = Callable[[Any], None]


class WorkerOperationController:
    """Own the lifecycle of the worker used by the main operation flow."""

    def __init__(self, window: Any, thread_pool: QThreadPool) -> None:
        self.window = window
        self.thread_pool = thread_pool

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
                "Operação em andamento",
                "Aguarde ou cancele a operação atual.",
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
            f"{done}/{total}  —  {item}  —  {elapsed:.1f}s decorridos"
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
                progress_text = "em andamento"
            if item:
                window._tree_loading_message = f"Carregando ({progress_text}): {item}"
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

    def worker_failed(self, message: str, detail: str) -> None:
        window = self.window
        self.append_log(f"FALHA: {message}")
        if detail.strip():
            self.append_log(f"Detalhes técnicos:\n{detail.rstrip()}")
        lowered = f"{message}\n{detail}".casefold()
        cancelled = bool(self.token and self.token.cancelled) or "cancel" in lowered
        self._set_state("CANCELLED" if cancelled else "FAILED")
        if cancelled:
            if getattr(window, "_tree_loading", False):
                window._set_tree_loading(False, "Carregamento cancelado.")
            if hasattr(window, "progress_label"):
                window.progress_label.setText("Operação cancelada.")
            window.statusBar().showMessage("Operação cancelada.", 5000)
            return

        if (
            hasattr(window, "connection_state")
            and window.stack.currentWidget() is window.pages.get("connection")
        ):
            source = window.source_by_combo(window.connection_source)
            if "401" in message or "autentica" in lowered or "sessão expirada" in lowered:
                state = "Falha de autenticação — credenciais inválidas ou sessão expirada"
                title = "Não foi possível entrar"
            elif "403" in message or "permiss" in lowered or "restrito" in lowered:
                state = "Acesso restrito — a conta não possui permissão para este conteúdo"
                title = "Página sem permissão"
            else:
                state = "Falha de comunicação — o Confluence está indisponível ou inacessível"
                title = "Confluence indisponível"
            window.connection_state.setText(state)
            if source:
                window.connection_states[source.id] = state
            QMessageBox.critical(window, title, f"{state}\n\n{message}")
            return

        QMessageBox.critical(window, "Operação não concluída", message)

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
                "Cancelar operação",
                "Deseja interromper a operação atual? Arquivos concluídos serão preservados.",
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.token.cancel()
        self._set_state("CANCELLED")
        if hasattr(window, "progress_label"):
            window.progress_label.setText(
                "Cancelamento solicitado. Finalizando a etapa atual…"
            )
