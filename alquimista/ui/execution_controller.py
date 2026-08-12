from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QMessageBox

from ..models import ProjectConfig
from ..runtime import CancellationToken
from ..services import ConsolidationService, ExtractionService, SourceRuntime
from ..storage import MANIFEST_NAME, ManifestStore
from .controllers import RuntimeBuilder
from .i18n import translate_text
from .project_controller import validate_project_snapshot


def prepare_runtimes(
    window: Any, project: ProjectConfig, token: CancellationToken, log: Any
) -> list[SourceRuntime]:
    return RuntimeBuilder(
        window.trees,
        window.secrets,
        window.connector_registry,
    ).build_connectors(project, token, log)


def run_extraction(
    window: Any, *, partial_update_keys: set[str] | None = None
) -> None:
    snapshot = window._validated_project_snapshot()
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
    operation = str(window.execution_mode.currentData()) if hasattr(window, "execution_mode") else "complete"
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
        failed: dict[str, list[str]] = {
            entry.source_id: []
            for entry in document.entries
            if entry.status.value in {"failed", "preserved_after_error"}
        }
        for entry in document.entries:
            if entry.status.value in {"failed", "preserved_after_error"}:
                failed.setdefault(entry.source_id, []).append(entry.page_id)
        if not any(failed.values()):
            QMessageBox.information(
                window,
                translate_text("Falhas"),
                translate_text("Não há páginas com falha para repetir."),
            )
            return
        original = {
            source.id: list(source.selected_page_ids)
            for source in window.project.sources
        }
        partial_update_keys = {
            f"{source_id}:{page_id}"
            for source_id, page_ids in failed.items()
            for page_id in page_ids
        }
        try:
            for source in window.project.sources:
                source.selected_page_ids = failed.get(source.id, [])
            # SelectionStore is the canonical source of truth for rendering.
            # The legacy mutation above did not update it, so rebuild it from
            # project.selections to avoid a stale store desync.
            window._rebuild_selection_store()
            window.project.extraction.force_reprocess = True
            window.run_extraction(partial_update_keys=partial_update_keys)
        finally:
            for source in window.project.sources:
                source.selected_page_ids = original[source.id]
            window.project.extraction.force_reprocess = False
    except Exception as exc:
        QMessageBox.warning(window, translate_text("Falhas"), str(exc))

def run_complete(window: Any) -> None:
    snapshot = window._validated_project_snapshot()
    if snapshot is None:
        return

    def work(token: CancellationToken, progress: Any, log: Any) -> dict[str, Any]:
        runtimes = window._prepare_runtimes(snapshot, token, log)
        extraction = ExtractionService(
            snapshot,
            runtimes,
            window._project_dir(),
            token=token,
            log=log,
            progress=progress,
        ).run()
        consolidation = ConsolidationService(
            snapshot,
            window._project_dir(),
            token=token,
            log=log,
            progress=progress,
        ).run()
        return {
            "extraction": extraction,
            "consolidation": consolidation,
            "output_dir": extraction["output_dir"],
            "duration_seconds": extraction["duration_seconds"]
            + consolidation["duration_seconds"],
        }

    window._start_worker(work, window._operation_done)

def validated_project_snapshot(window: Any) -> ProjectConfig | None:
    """Validate operation-specific prerequisites before creating a worker."""
    try:
        window._sync_project_ui()
        snapshot = validate_project_snapshot(window.project)
        operation = (
            str(window.execution_mode.currentData())
            if hasattr(window, "execution_mode")
            else "complete"
        )
        if operation not in {"complete", "extract", "consolidate"}:
            raise ValueError(translate_text("Escolha uma operação válida antes de executar."))
        if not snapshot.output_dir.strip():
            raise ValueError(translate_text("Defina uma pasta de saída antes de executar."))
        if operation == "consolidate":
            manifest = window._base_path() / MANIFEST_NAME
            if not manifest.is_file():
                raise ValueError(
                    translate_text(
                        "Não foi possível consolidar porque o manifesto da consolidação "
                        "ainda não foi criado. Execute primeiro a extração ou gere uma prévia."
                    )
                )
            return snapshot
        active = [source for source in snapshot.sources if source.enabled]
        if not active:
            raise ValueError(translate_text("Adicione e ative ao menos uma fonte antes de executar."))
        selected = sum(
            len(snapshot.selected_keys_for(source.id)) for source in active
        )
        if selected == 0:
            raise ValueError(
                translate_text(
                    "Nenhuma fonte ativa possui documentos selecionados. "
                    "Volte à seleção, marque ao menos uma página e tente novamente."
                )
            )
        if not snapshot.markdown.metadata_style.strip():
            raise ValueError(translate_text("Configure o formato Markdown antes de executar."))
        return snapshot
    except Exception as exc:
        QMessageBox.warning(window, translate_text("Configuração inválida"), str(exc))
        return None
