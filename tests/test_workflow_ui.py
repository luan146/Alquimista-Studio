"""Guided workflow: 5-step navigation, Início, run blocker, results and recent projects."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QMessageBox

from alquimista.models import EntryStatus, KnowledgeSelection, ManifestDocument, ManifestEntry, SourceConfig
from alquimista.storage import (
    MANIFEST_NAME,
    REPORT_NAME,
    append_history,
    load_history,
    save_project,
)
from alquimista.ui.controllers.operation_controller import progress_eta
from alquimista.ui.i18n import LanguageManager
from alquimista.ui.main_window import MainWindow


@pytest.fixture
def window(qtbot: Any, tmp_path: Path) -> MainWindow:
    # Private settings: recent projects must not touch the user's real ones.
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    manager = LanguageManager(QApplication.instance(), settings)
    manager.set_language("pt-BR", persist=False)
    created = MainWindow(language_manager=manager)
    # Not qtbot.addWidget: pytest-qt would close it before this fixture can clear
    # the pending-edits flag; conftest's cleanup closes MainWindows safely.
    yield created
    created.dirty = False


def _with_source_and_selection(window: MainWindow) -> SourceConfig:
    source = SourceConfig(
        id="docs", name="Docs", source_type="local_files", base_url="C:/docs", connector_options={"path": "C:/docs"}
    )
    window.project.sources = [source]
    window.project.selections = [KnowledgeSelection(source_id="docs", container_id="root", document_id="a")]
    window._refresh_source_widgets()
    return source


def test_sidebar_has_home_plus_five_steps_and_old_keys_still_route(window: MainWindow) -> None:
    assert list(window.nav_buttons) == ["dashboard", "sources", "selection", "format", "extraction", "results"]

    window._show_page("connection")
    assert window.stack.currentWidget() is window.pages["sources"]
    window._show_page("consolidation")
    assert window.stack.currentWidget() is window.pages["format"]
    assert window.format_tabs.currentWidget() is window.pages["consolidation"]
    window._show_page("markdown")
    assert window.format_tabs.currentWidget() is window.pages["markdown"]


def test_step_status_and_footer_follow_the_project(window: MainWindow) -> None:
    window._show_page("sources")
    assert window.nav_status["sources"].text() == "●"
    assert window.nav_status["selection"].text() == "○"
    assert window.step_next_button.property("target") == "selection"

    _with_source_and_selection(window)
    window._show_page("format")

    assert window.nav_status["sources"].text() == "✓"
    assert window.nav_status["selection"].text() == "✓"
    assert window.nav_status["format"].text() == "●"
    window._go_step("back")
    assert window.stack.currentWidget() is window.pages["selection"]


def test_run_is_blocked_with_the_reason_until_pages_are_selected(
    window: MainWindow, monkeypatch: pytest.MonkeyPatch
) -> None:
    started: list[str] = []
    monkeypatch.setattr(window, "run_complete", lambda: started.append("run"))
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    window._show_page("extraction")
    assert not window.execute_button.isEnabled()
    assert "Adicione uma fonte" in window.execute_blocker.text()
    window.execute_selected_operation()
    assert not started

    _with_source_and_selection(window)
    window._show_page("extraction")
    assert window.execute_button.isEnabled()
    assert window.execute_blocker.isHidden()
    window.execute_selected_operation()
    assert started == ["run"]


def test_output_actions_use_the_output_folder_not_the_project_folder(window: MainWindow, tmp_path: Path) -> None:
    window.project_path = tmp_path / "projeto.json"
    window.project.output_dir = "base"
    (tmp_path / "base").mkdir()
    (tmp_path / "base" / MANIFEST_NAME).write_text('{"entries": []}', encoding="utf-8")

    assert window._base_path() == tmp_path / "base"
    assert window._execution_blocker() is not None  # no source yet
    window.execution_mode.setCurrentIndex(window.execution_mode.findData("consolidate"))
    assert window._execution_blocker() is None  # manifest found in the output folder


def test_recent_projects_are_remembered_and_reopened(window: MainWindow, tmp_path: Path) -> None:
    project_file = tmp_path / "meu projeto.json"
    save_project(project_file, window.project.model_copy(update={"project_name": "Base de suporte"}))

    window._load_project_file_into_window(project_file)
    assert window.project.project_name == "Base de suporte"
    window._show_page("dashboard")
    assert window.home_recent_list.count() == 1

    window.new_project()
    window.reopen_last_project()
    assert window.project_path == project_file.resolve()


def test_home_switches_from_first_steps_to_project_overview(window: MainWindow) -> None:
    window._show_page("dashboard")
    assert window.home_empty.isVisibleTo(window) and not window.home_overview.isVisibleTo(window)

    _with_source_and_selection(window)
    window._refresh_home()

    assert window.home_overview.isVisibleTo(window) and not window.home_empty.isVisibleTo(window)
    assert window.home_metrics["selection"][0].text() == "1"
    assert "Executar" in window.home_continue_button.text()


def test_results_show_failures_from_the_manifest_and_the_run_history(window: MainWindow, tmp_path: Path) -> None:
    window.project_path = tmp_path / "projeto.json"
    output = tmp_path / window.project.output_dir
    output.mkdir()
    failed = ManifestEntry(
        source_id="docs", source_name="Docs", page_id="a", document_id="a", document_key="docs:root:a",
        title="Guia", source_url="https://docs.example.com/a", status=EntryStatus.FAILED, error_message="HTTP 500",
    )
    manifest = ManifestDocument(project_id=window.project.project_id, entries=[failed])
    (output / MANIFEST_NAME).write_text(manifest.model_dump_json(), encoding="utf-8")
    report = {"executed_at": "2026-10-10T08:00:00+00:00", "duration_seconds": 3.5, "counters": {"new": 2}, "failures": 1}
    (output / REPORT_NAME).write_text(json.dumps(report), encoding="utf-8")
    append_history(output, {**report, "executed_at": "2026-10-09T08:00:00+00:00"}, status="cancelled")
    append_history(output, report)

    window._show_page("results")

    assert window.results_body.isVisibleTo(window)
    assert window.result_failures_table.item(0, 0).text() == "Guia"
    assert window.result_failures_table.item(0, 2).text() == "HTTP 500"
    assert window.retry_failures_button.isEnabled()
    assert window.result_history_table.rowCount() == 2
    assert window.result_history_table.item(0, 2).text() == "2"
    assert window.result_history_table.item(0, 1).text() == "3.5s"
    assert window.result_history_table.item(1, 1).text() == "3.5s (cancelada)"


def test_history_keeps_newest_first(tmp_path: Path) -> None:
    for number in range(3):
        append_history(tmp_path, {"executed_at": f"run-{number}", "counters": {}})
    assert [run["executed_at"] for run in load_history(tmp_path)] == ["run-2", "run-1", "run-0"]


def test_progress_shows_rate_and_time_left_once_measurable() -> None:
    assert progress_eta(1, 100, 2) == "2s decorridos"
    assert progress_eta(30, 90, 60) == "1 min decorridos · 30/min · ~2 min restantes"
