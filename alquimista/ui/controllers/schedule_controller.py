"""Settings card that creates the daily Windows task running ``--sync``."""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMessageBox

from ... import scheduler
from ...errors import AlquimistaError
from ..i18n import translate_text
from ..workers import Worker


def refresh_schedule_status(window: Any) -> None:
    """Show whether the saved project has a daily task (queried off the UI thread)."""
    path = window.project_path
    if path is None:
        window.schedule_status.setText(translate_text("Salve o projeto para poder agendar."))
        return
    window.schedule_status.setText(translate_text("Consultando o Agendador de Tarefas…"))
    worker = Worker(lambda _token, _progress, _log: scheduler.scheduled_time(path))

    def done(at: str | None) -> None:
        if window.project_path != path:
            return
        window.schedule_status.setText(
            translate_text("Agendado todos os dias às {time}.").format(time=at)
            if at
            else translate_text("Nenhum agendamento para este projeto.")
        )

    worker.signals.succeeded.connect(done)
    worker.signals.failed.connect(lambda error, _details: window.schedule_status.setText(str(error)))
    window.schedule_worker = worker
    window.thread_pool.start(worker)


def schedule_daily(window: Any) -> None:
    # The task runs the file on disk, so pending edits must be saved first.
    if (window.project_path is None or window.dirty) and not window.save_project():
        return
    at = window.schedule_time.time().toString("HH:mm")
    try:
        scheduler.schedule_daily(window.project_path, at)
    except AlquimistaError as exc:
        QMessageBox.warning(window, translate_text("Agendamento não criado"), str(exc))
        return
    QMessageBox.information(
        window,
        translate_text("Sincronização agendada"),
        translate_text(
            "O projeto será sincronizado e consolidado todos os dias às {time}, com o computador ligado "
            "e você conectado ao Windows.\n\nFontes com token precisam da opção “Lembrar neste "
            "computador”. Fontes com login pelo navegador usam a sessão salva; quando ela expirar, "
            "faça login de novo. O resultado fica no relatório de sincronização e no log técnico."
        ).format(time=at),
    )
    refresh_schedule_status(window)


def remove_schedule(window: Any) -> None:
    if window.project_path is None:
        return
    try:
        scheduler.remove_schedule(window.project_path)
    except AlquimistaError as exc:
        QMessageBox.warning(window, translate_text("Agendamento não removido"), str(exc))
    refresh_schedule_status(window)
