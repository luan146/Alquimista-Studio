"""Guided workflow: step status, Próximo/Voltar, Início panel, recent projects,
shortcuts, run blockers and the end-of-run notification."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
    QTableWidgetItem,
)

from ...models import AuthMode, ManifestEntry, SourceConfig
from ...session_store import session_exists
from ...storage import MANIFEST_NAME, REPORT_NAME, ManifestStore, load_history
from ..components import NAVIGATION, WORKFLOW_STEPS
from ..i18n import translate_text
from ..recent_projects import recent_projects, remember_project
from . import WindowBase

STEP_LABELS = dict(NAVIGATION)
DONE, CURRENT, PENDING = "✓", "●", "○"


class WorkflowMixin(WindowBase):
    """Behavior shared by the sidebar, the Início page and the run page."""

    project: Any
    project_path: Path | None
    secrets: Any
    connector_registry: Any
    connected_sources: Any
    ui_settings: Any
    stack: Any
    pages: dict[str, Any]
    nav_status: dict[str, Any]
    dirty: bool
    worker: Any
    src_platform: Any
    source_url_input: Any
    add_source_dialog: Any
    home_empty: Any
    home_overview: Any
    home_metrics: dict[str, Any]
    home_next_title: Any
    home_next_detail: Any
    home_continue_button: Any
    home_recent_list: Any
    home_recent_empty: Any
    result_failures_table: Any
    result_failures_label: Any
    result_history_table: Any
    retry_failures_button: Any
    step_back_button: Any
    step_next_button: Any
    step_footer: Any
    execute_button: Any
    execute_blocker: Any
    execution_mode: Any
    _show_page: Any
    _base_path: Any
    _confirm_discard: Any
    _load_project_file_into_window: Any
    open_project: Any
    new_project: Any
    save_project: Any
    save_project_as: Any
    execute_selected_operation: Any
    load_tree: Any
    _pick_local_folder: Any
    _selection_source: Any
    trees: Any

    # --- sources -----------------------------------------------------------

    def _real_sources(self) -> list[SourceConfig]:
        """Sources the user added (the blank placeholder of a new project is not one)."""
        return [
            source
            for source in self.project.sources
            if source.base_url or source.connector_options.get("source_url")
        ]

    def _credentials_available(self, source: SourceConfig) -> bool:
        if source.id in self.connected_sources:
            return True
        if source.source_type == "local_files" or source.auth_mode == AuthMode.PUBLIC:
            return True
        if source.auth_mode == AuthMode.BROWSER:
            return session_exists(source.id)
        return bool(self.secrets.get(source.id, ""))

    def _source_connection_badge(self, source: SourceConfig) -> str:
        try:
            descriptor = self.connector_registry.get(source.source_type)
        except ValueError:
            return translate_text("⚠ Conector não registrado")
        if not descriptor.runnable:
            return translate_text("Em desenvolvimento")
        if source.id in self.connected_sources:
            return translate_text("● Conectada")
        if source.source_type == "local_files":
            return translate_text("● Pasta local")
        if source.auth_mode == AuthMode.BROWSER:
            return (
                translate_text("◐ Sessão salva — testar")
                if session_exists(source.id)
                else translate_text("○ Fazer login")
            )
        if source.auth_mode in {AuthMode.BASIC, AuthMode.BEARER}:
            return (
                translate_text("◐ Token informado — testar")
                if self.secrets.get(source.id, "")
                else translate_text("○ Sem token")
            )
        return translate_text("◐ Público — testar")

    def open_add_source_dialog(self) -> None:
        self._show_page("sources")
        self.add_source_dialog.open_for_add()

    def _source_card_clicked(self, source_type: str) -> None:
        """Catalog card: preselect the platform and ask for its URL (or folder)."""
        self._show_page("sources")
        platform_index = self.src_platform.findData(source_type)
        if platform_index >= 0:
            self.src_platform.setCurrentIndex(platform_index)
        if source_type == "local_files":
            self.add_source_dialog.reject()
            self._pick_local_folder()
            return
        try:
            name = self.connector_registry.get(source_type).display_name
        except ValueError:
            name = source_type
        self.source_url_input.setPlaceholderText(
            translate_text("Cole aqui a URL do {platform}").format(platform=name)
        )
        self.source_url_input.setFocus()

    # --- steps ---------------------------------------------------------------

    def _selected_count(self) -> int:
        return sum(
            len(self.project.selected_keys_for(source.id))
            for source in self.project.sources
            if source.enabled
        )

    def _last_report(self) -> dict[str, Any] | None:
        path = self._base_path() / REPORT_NAME
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) else None

    def _step_done(self) -> dict[str, bool]:
        sources = [source for source in self._real_sources() if source.enabled]
        has_sources = bool(sources) and any(self._credentials_available(s) for s in sources)
        has_selection = self._selected_count() > 0
        has_run = (self._base_path() / REPORT_NAME).is_file()
        return {
            "sources": has_sources,
            "selection": has_selection,
            # Markdown and packages start with working defaults.
            "format": has_sources and has_selection,
            "extraction": has_run,
            "results": has_run,
        }

    def _next_pending_step(self) -> str:
        done = self._step_done()
        return next((key for key in WORKFLOW_STEPS if not done[key]), "results")

    def _current_page_key(self) -> str:
        current = self.stack.currentWidget()
        return next(
            (key for key, _label in NAVIGATION if self.pages.get(key) is current),
            "settings",
        )

    def _refresh_workflow_state(self) -> None:
        if not hasattr(self, "nav_status"):
            return
        done = self._step_done()
        current = self._current_page_key()
        for key, label in self.nav_status.items():
            label.setText(CURRENT if key == current else DONE if done.get(key) else PENDING)
            label.setToolTip(
                translate_text("Etapa concluída")
                if done.get(key)
                else translate_text("Etapa pendente")
            )
        self._refresh_step_footer(current)
        self._refresh_execute_blocker()
        if current == "dashboard":
            self._refresh_home()

    def _schedule_workflow_refresh(self) -> None:
        # Edits fire many signals; refresh the sidebar once they settle.
        timer = getattr(self, "_workflow_timer", None)
        if timer is None:
            timer = QTimer(self)
            timer.setSingleShot(True)
            timer.setInterval(150)
            timer.timeout.connect(self._refresh_workflow_state)
            self._workflow_timer = timer
        timer.start()

    def _refresh_step_footer(self, current: str) -> None:
        if not hasattr(self, "step_footer"):
            return
        if current not in WORKFLOW_STEPS:
            self.step_footer.setVisible(False)
            return
        self.step_footer.setVisible(True)
        index = WORKFLOW_STEPS.index(current)
        previous = WORKFLOW_STEPS[index - 1] if index else "dashboard"
        self.step_back_button.setText(
            translate_text("← {step}").format(step=translate_text(STEP_LABELS[previous]))
        )
        self.step_back_button.setProperty("target", previous)
        following = WORKFLOW_STEPS[index + 1] if index + 1 < len(WORKFLOW_STEPS) else None
        self.step_next_button.setVisible(following is not None)
        if following:
            self.step_next_button.setText(
                translate_text("Próximo: {step} →").format(step=translate_text(STEP_LABELS[following]))
            )
            self.step_next_button.setProperty("target", following)

    def _go_step(self, which: str) -> None:
        target = (self.step_back_button if which == "back" else self.step_next_button).property("target")
        if target:
            self._show_page(str(target))

    def _continue_workflow(self) -> None:
        self._show_page(self._next_pending_step())

    # --- Início ----------------------------------------------------------------

    def _refresh_home(self) -> None:
        if not hasattr(self, "home_overview"):
            return
        sources = self._real_sources()
        self.home_empty.setVisible(not sources)
        self.home_overview.setVisible(bool(sources))
        self._refresh_recent_list()
        if not sources:
            return
        ready = sum(1 for source in sources if self._credentials_available(source))
        self._set_home_metric(
            "sources",
            str(len(sources)),
            translate_text("{ready} com acesso configurado").format(ready=ready),
        )
        selected = self._selected_count()
        self._set_home_metric(
            "selection",
            str(selected),
            translate_text("páginas selecionadas") if selected else translate_text("nenhuma página ainda"),
        )
        report = self._last_report()
        if report:
            counters = report.get("counters", {})
            when = self._format_when(str(report.get("executed_at", "")))
            self._set_home_metric(
                "last_run",
                when,
                translate_text("{new} novos · {updated} alterados · {failures} falhas").format(
                    new=counters.get("new", 0),
                    updated=counters.get("updated", 0),
                    failures=report.get("failures", 0),
                ),
            )
        else:
            self._set_home_metric("last_run", "—", translate_text("ainda não executado"))
        cached = getattr(self, "_home_schedule", None)
        if self.project_path is None:
            self._set_home_metric("schedule", "—", translate_text("salve o projeto primeiro"))
        elif cached and cached[0] == self.project_path:
            self._set_home_metric("schedule", *cached[1])
        else:
            self._set_home_metric("schedule", "…", translate_text("consultando"))
        next_key = self._next_pending_step()
        done = self._step_done()
        if all(done.values()):
            self.home_next_title.setText(translate_text("Tudo pronto"))
            self.home_next_detail.setText(
                translate_text(
                    "A base já foi gerada. Use “Sincronizar agora” para baixar só o que mudou nas fontes."
                )
            )
            self.home_continue_button.setText(translate_text("Ver resultados →"))
        else:
            hints = {
                "sources": translate_text("Conecte as fontes: informe o token ou faça login pelo navegador."),
                "selection": translate_text("Escolha os espaços e páginas que entram na base."),
                "format": translate_text("Revise o formato do Markdown e os pacotes para IA."),
                "extraction": translate_text("Tudo configurado: execute a extração."),
                "results": translate_text("Veja o resultado da última execução."),
            }
            self.home_next_title.setText(
                translate_text("Próximo passo: {step}").format(step=translate_text(STEP_LABELS[next_key]))
            )
            self.home_next_detail.setText(hints[next_key])
            self.home_continue_button.setText(
                translate_text("Continuar: {step} →").format(step=translate_text(STEP_LABELS[next_key]))
            )
        if hasattr(self, "home_sync_button"):
            self.home_sync_button.setEnabled(done["extraction"])

    def _set_home_metric(self, key: str, value: str, detail: str) -> None:
        value_label, detail_label = self.home_metrics[key]
        value_label.setText(value)
        detail_label.setText(detail)
        detail_label.setVisible(True)

    @staticmethod
    def _format_when(raw: str) -> str:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone().strftime("%d/%m %H:%M")
        except ValueError:
            return raw or "—"

    # --- projects ----------------------------------------------------------

    def _refresh_recent_list(self) -> None:
        if not hasattr(self, "home_recent_list"):
            return
        self.home_recent_list.clear()
        for path in recent_projects(self.ui_settings):
            item = QListWidgetItem(f"{path.stem}    —    {path.parent}")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            item.setToolTip(str(path))
            self.home_recent_list.addItem(item)
        has_items = self.home_recent_list.count() > 0
        self.home_recent_list.setVisible(has_items)
        self.home_recent_empty.setVisible(not has_items)

    def _remember_current_project(self) -> None:
        if self.project_path is not None:
            remember_project(self.ui_settings, self.project_path)

    def open_project_path(self, path: str | Path) -> None:
        if not self._confirm_discard():
            return
        self._load_project_file_into_window(Path(path))

    def _project_menu(self) -> QMenu:
        """Built on demand so it always shows translated labels and current recents."""
        menu = QMenu(self)
        menu.addAction(translate_text("➕ Novo projeto") + "\tCtrl+N", self.new_project)
        menu.addAction(translate_text("📂 Abrir projeto…") + "\tCtrl+O", self.open_project)
        recent = menu.addMenu(translate_text("Recentes"))
        paths = recent_projects(self.ui_settings)
        for path in paths:
            recent.addAction(path.stem, partial(self.open_project_path, path)).setToolTip(str(path))
        recent.setEnabled(bool(paths))
        menu.addSeparator()
        menu.addAction(translate_text("💾 Salvar") + "\tCtrl+S", self.save_project)
        menu.addAction(translate_text("Salvar como…") + "\tCtrl+Shift+S", self.save_project_as)
        return menu

    def _install_shortcuts(self) -> None:
        bindings: list[tuple[QKeySequence, Callable[[], object]]] = [
            (QKeySequence(QKeySequence.StandardKey.New), self.new_project),
            (QKeySequence(QKeySequence.StandardKey.Open), self.open_project),
            (QKeySequence(QKeySequence.StandardKey.Save), self.save_project),
            (QKeySequence("Ctrl+Shift+S"), self.save_project_as),
            (QKeySequence("F5"), self.execute_selected_operation),
            (QKeySequence("Ctrl+0"), partial(self._show_page, "dashboard")),
        ]
        bindings.extend(
            (QKeySequence(f"Ctrl+{number}"), partial(self._show_page, key))
            for number, key in enumerate(WORKFLOW_STEPS, start=1)
        )
        for sequence, slot in bindings:
            shortcut = QShortcut(sequence, self)
            shortcut.activated.connect(slot)

    # --- run page ------------------------------------------------------------

    def _execution_blocker(self) -> tuple[str, str] | None:
        """(message, page to fix it) when the chosen operation cannot run yet."""
        operation = str(self.execution_mode.currentData()) if hasattr(self, "execution_mode") else "complete"
        if operation == "consolidate":
            if not (self._base_path() / MANIFEST_NAME).is_file():
                return translate_text(
                    "Ainda não há páginas extraídas para consolidar. Escolha “Extrair e consolidar”."
                ), ""
            return None
        if not [source for source in self._real_sources() if source.enabled]:
            return translate_text("Adicione uma fonte antes de executar."), "sources"
        if self._selected_count() == 0:
            return translate_text("Selecione as páginas em Seleção antes de executar."), "selection"
        return None

    def _refresh_execute_blocker(self) -> None:
        if not hasattr(self, "execute_button"):
            return
        blocker = None if self.worker is not None else self._execution_blocker()
        self.execute_button.setEnabled(self.worker is None and blocker is None)
        self.execute_blocker.setVisible(blocker is not None)
        if blocker is not None:
            message, target = blocker
            link = (
                f' <a href="{target}" style="color:#42B8BE;">{translate_text("Ir para a etapa")}</a>'
                if target
                else ""
            )
            self.execute_blocker.setText(f"⚠ {message}{link}")

    def _maybe_autoload_tree(self) -> None:
        """Entering Seleção with working access loads the spaces without an extra click."""
        source = self._selection_source()
        if (
            source is None
            or source.id in self.trees
            or getattr(self, "_tree_loading", False)
            or self.worker is not None
            or source not in self._real_sources()
        ):
            return
        if source.id in self.connected_sources or self._credentials_available(source):
            QTimer.singleShot(0, self.load_tree)

    # --- results ---------------------------------------------------------------

    def _refresh_results_tables(self) -> None:
        """Failures of the manifest (with origin links) and the run history."""
        if not hasattr(self, "result_failures_table"):
            return
        failed: list[ManifestEntry] = []
        try:
            entries = ManifestStore(self._base_path() / MANIFEST_NAME, self.project).load().entries
            failed = [
                entry
                for entry in entries
                if entry.status.value in {"failed", "preserved_after_error"}
            ]
        except Exception:  # missing/old manifest: just show no failures
            failed = []
        table = self.result_failures_table
        table.setRowCount(len(failed))
        self._failure_urls = [entry.source_url for entry in failed]
        for row, entry in enumerate(failed):
            for column, value in enumerate((entry.title, entry.source_name, entry.error_message)):
                table.setItem(row, column, QTableWidgetItem(str(value or "")))
        self.retry_failures_button.setEnabled(bool(failed))
        self.result_failures_label.setText(
            translate_text("{count} documento(s) com falha. Clique duas vezes para abrir na origem.").format(
                count=len(failed)
            )
            if failed
            else translate_text("Nenhuma falha na última execução.")
        )
        runs = load_history(self._base_path())
        history = self.result_history_table
        history.setRowCount(len(runs))
        for row, run in enumerate(runs):
            counters = run.get("counters") or {}
            values = (
                self._format_when(str(run.get("executed_at", ""))),
                f"{run.get('duration_seconds') or 0}s",
                counters.get("new", 0),
                counters.get("updated", 0),
                counters.get("unchanged", 0),
                run.get("failures", 0),
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if column:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                history.setItem(row, column, item)

    def _open_failure_origin(self, row: int) -> None:
        urls = getattr(self, "_failure_urls", [])
        if 0 <= row < len(urls) and urls[row]:
            QDesktopServices.openUrl(QUrl(urls[row]))

    # --- notifications -----------------------------------------------------

    def _notify_finished(self, title: str, message: str) -> None:
        """Flash the taskbar and, when the window is in the background, show a toast."""
        QApplication.alert(self, 0)
        if self.isActiveWindow() or not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = getattr(self, "_tray", None)
        if tray is None:
            tray = QSystemTrayIcon(self.windowIcon(), self)
            tray.messageClicked.connect(self._bring_to_front)
            self._tray = tray
        tray.show()
        tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 10000)
        QTimer.singleShot(15000, tray.hide)

    def _bring_to_front(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _confirm_open_failure(self, path: Path, error: Exception) -> None:
        QMessageBox.critical(
            self,
            translate_text("Projeto inválido"),
            translate_text("Não foi possível abrir {path}:\n{error}").format(path=path, error=error),
        )
