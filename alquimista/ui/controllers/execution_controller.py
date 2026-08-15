from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMessageBox

from ...models import KnowledgeSelection, ProjectConfig
from ...runtime import CancellationToken
from ...services import ConsolidationService, ExtractionService, SourceRuntime
from ...storage import MANIFEST_NAME, ManifestStore
from ..i18n import translate_text
from .project_controller import validate_project_snapshot
from .runtime_controller import RuntimeBuilder


def prepare_runtimes(
    window: Any,
    project: ProjectConfig,
    token: CancellationToken,
    log: Any,
    *,
    allow_empty_selection: bool = False,
) -> list[SourceRuntime]:
    return RuntimeBuilder(
        window.trees,
        window.secrets,
        window.connector_registry,
    ).build_connectors(project, token, log, allow_empty_selection=allow_empty_selection)



def run_extraction(
    window: Any,
    *,
    partial_update_keys: set[str] | None = None,
    project_override: ProjectConfig | None = None,
) -> None:
    snapshot = project_override or window._validated_project_snapshot()
    if snapshot is None:
        return

    def work(token: CancellationToken, progress: Any, log: Any) -> dict[str, Any]:
        runtimes = window._prepare_runtimes(snapshot, token, log)
        return ExtractionService(
            snapshot,
            runtimes,
            window._project_dir(),
            partial_update_keys=partial_update_keys,
            token=token,
            log=log,
            progress=progress,
        ).run()

    window._start_worker(work, window._operation_done)


def execute_selected_operation(window: Any) -> None:
    """Executa a opção escolhida no fluxo único da aplicação."""
    operation = (
        str(window.execution_mode.currentData())
        if hasattr(window, "execution_mode")
        else "complete"
    )
    if operation == "extract":
        window.run_extraction()
    elif operation == "consolidate":
        window.run_consolidation()
    else:
        window.run_complete()


def retry_failures(window: Any) -> None:
    try:
        document = ManifestStore(
            window._base_path() / MANIFEST_NAME, window.project
        ).load()
        failed_entries = [
            entry
            for entry in document.entries
            if entry.status.value in {"failed", "preserved_after_error"}
        ]
        if not failed_entries:
            QMessageBox.information(
                window,
                translate_text("Falhas"),
                translate_text("Não há páginas com falha para repetir."),
            )
            return
        partial_update_keys = {
            entry.document_key
            if entry.document_key.count(":") >= 2
            else f"{entry.source_id}:{entry.container_id or entry.space_key or '__legacy__'}:{entry.page_id}"
            for entry in failed_entries
        }
        failed_keys = set(partial_update_keys)
        retry_project = window.project.model_copy(deep=True)
        retry_project.selections = [
            KnowledgeSelection(
                source_id=entry.source_id,
                container_id=entry.container_id or entry.space_key or "__legacy__",
                document_id=entry.document_id or entry.page_id,
                selected=True,
            )
            for entry in failed_entries
        ]
        for source in retry_project.sources:
            source.selected_page_ids = [
                entry.document_id or entry.page_id
                for entry in failed_entries
                if entry.source_id == source.id
            ]
        retry_project.extraction.force_reprocess = True

        def work(token: CancellationToken, progress: Any, log: Any) -> dict[str, Any]:
            runtimes = window._prepare_runtimes(retry_project, token, log)
            return ExtractionService(
                retry_project,
                runtimes,
                window._project_dir(),
                partial_update_keys=failed_keys,
                token=token,
                log=log,
                progress=progress,
            ).run()

        window._start_worker(work, window._operation_done)
    except Exception as exc:
        QMessageBox.critical(
            window,
            translate_text("Erro"),
            f"{translate_text('Não foi possível iniciar a repetição')}: {exc}",
        )


def run_consolidation(
    window: Any,
    *,
    selected_keys: set[str] | None = None,
    project_override: ProjectConfig | None = None,
) -> None:
    snapshot = project_override or window._validated_project_snapshot()
    if snapshot is None:
        return

    def work(token: CancellationToken, progress: Any, log: Any) -> dict[str, Any]:
        return ConsolidationService(
            snapshot,
            window._project_dir(),
            selected_keys=selected_keys,
            token=token,
            log=log,
            progress=progress,
        ).run()

    window._start_worker(work, window._operation_done)


def run_complete(window: Any) -> None:
    snapshot = window._validated_project_snapshot()
    if snapshot is None:
        return

    def work(token: CancellationToken, progress: Any, log: Any) -> dict[str, Any]:
        runtimes = window._prepare_runtimes(snapshot, token, log)
        extraction_report = ExtractionService(
            snapshot,
            runtimes,
            window._project_dir(),
            token=token,
            log=log,
            progress=progress,
        ).run()
        token.check()
        consolidation_report = ConsolidationService(
            snapshot,
            window._project_dir(),
            token=token,
            log=log,
            progress=progress,
        ).run()
        return {
            "mode": "complete",
            "extraction": extraction_report,
            "consolidation": consolidation_report,
            "packages": consolidation_report.get("packages", 0),
            "pages": consolidation_report.get("pages", 0),
            "duration_seconds": round(
                extraction_report.get("duration_seconds", 0.0)
                + consolidation_report.get("duration_seconds", 0.0),
                2,
            ),
        }

    window._start_worker(work, window._operation_done)


def sync_source(window: Any, source_id: str) -> None:
    snapshot = window._validated_project_snapshot()
    if snapshot is None:
        return
    source = next((s for s in snapshot.sources if s.id == source_id), None)
    if not source:
        QMessageBox.warning(
            window,
            translate_text("Fonte não encontrada"),
            translate_text("A fonte selecionada não está configurada neste projeto."),
        )
        return
    from ...services.sync import IncrementalSyncService, SyncScope
    from ..dialogs.sync_dialog import SyncPreviewDialog

    token = CancellationToken()
    log = window.technical_logger.info
    runtimes = prepare_runtimes(window, snapshot, token, log, allow_empty_selection=True)
    service = IncrementalSyncService(snapshot, window._project_dir())
    dialog = SyncPreviewDialog(
        window,
        service,
        runtimes,
        scope=SyncScope.SOURCE,
        target_source_id=source_id,
        source_name=source.name,
    )
    dialog.exec()


def sync_project(window: Any) -> None:
    snapshot = window._validated_project_snapshot()
    if snapshot is None:
        return
    if not any(s.enabled for s in snapshot.sources):
        QMessageBox.warning(
            window,
            translate_text("Nenhuma fonte ativa"),
            translate_text("Ative ao menos uma fonte para sincronizar."),
        )
        return
    from ...services.sync import IncrementalSyncService, SyncScope
    from ..dialogs.sync_dialog import SyncPreviewDialog

    token = CancellationToken()
    log = window.technical_logger.info
    runtimes = prepare_runtimes(window, snapshot, token, log, allow_empty_selection=True)
    service = IncrementalSyncService(snapshot, window._project_dir())
    dialog = SyncPreviewDialog(
        window,
        service,
        runtimes,
        scope=SyncScope.PROJECT,
        source_name=snapshot.project_name or "Todas as Fontes",
    )
    dialog.exec()


def sync_selection(window: Any) -> None:
    snapshot = window._validated_project_snapshot()
    if snapshot is None:
        return
    from ...services.sync import IncrementalSyncService, SyncScope
    from ..dialogs.sync_dialog import SyncPreviewDialog

    token = CancellationToken()
    log = window.technical_logger.info
    runtimes = prepare_runtimes(window, snapshot, token, log, allow_empty_selection=False)
    service = IncrementalSyncService(snapshot, window._project_dir())
    dialog = SyncPreviewDialog(
        window,
        service,
        runtimes,
        scope=SyncScope.SELECTION,
        source_name="Seleção Atual",
    )
    dialog.exec()





def validated_project_snapshot(window: Any) -> ProjectConfig | None:
    try:
        return validate_project_snapshot(window.project)
    except Exception as exc:
        QMessageBox.critical(
            window,
            translate_text("Erro no projeto"),
            f"{translate_text('A configuração do projeto é inválida')}: {exc}",
        )
        return None


__all__ = [

    "execute_selected_operation",
    "prepare_runtimes",
    "retry_failures",
    "run_complete",
    "run_consolidation",
    "run_extraction",
    "sync_project",
    "sync_selection",
    "sync_source",
    "validated_project_snapshot",
]
