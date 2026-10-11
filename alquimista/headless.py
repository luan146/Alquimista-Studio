"""Synchronize a saved project without opening the window (Windows Task Scheduler)."""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .runtime import CancellationToken
from .services.sync import IncrementalSyncService, SyncOptions, SyncScope, add_to_selection
from .storage import load_project, save_project
from .ui.controllers.runtime_controller import RuntimeBuilder, RuntimeSecrets

EXIT_OK, EXIT_WITH_FAILURES, EXIT_ERROR = 0, 1, 2


def sync_project(project_path: Path, log: Callable[[str], None]) -> int:
    """Plan and apply an incremental sync of every enabled source, then consolidate."""
    try:
        project = load_project(project_path)
        secrets = RuntimeSecrets()
        secrets.load_remembered(project.sources, log)
        token = CancellationToken()
        runtimes = RuntimeBuilder({}, secrets).build_connectors(project, token, log, allow_empty_selection=True)
        service = IncrementalSyncService(project, project_path.resolve().parent, token=token, log=log)
        plan = service.plan_sync(runtimes, scope=SyncScope.PROJECT)
        log(
            f"[Agendado] {project.project_name}: {plan.new_count} novos, "
            f"{plan.updated_count} alterados, {plan.removed_count} removidos."
        )
        options = SyncOptions(delete_removed_files=project.extraction.delete_removed_files)
        report = service.apply_sync(plan, runtimes, options=options)
        if add_to_selection(project, report.added_selections):
            save_project(project_path, project)
    except Exception as exc:
        # Typically an expired browser session or token: the user must log in again.
        log(f"[Agendado] Sincronização de {project_path} não executada: {exc}")
        return EXIT_ERROR
    for failure in report.failures:
        log(f"[Agendado] Falha: {failure}")
    log(f"[Agendado] Concluída em {report.duration_seconds}s com {len(report.failures)} falha(s).")
    return EXIT_WITH_FAILURES if report.failures else EXIT_OK
