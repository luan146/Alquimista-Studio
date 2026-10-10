"""Usability round: whole-space selection, real preview, banners, sidebar, drag and drop, sample project."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QMimeData, QPointF, QSettings, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QApplication, QScrollArea

from alquimista.models import KnowledgeDocument, SourceConfig
from alquimista.runtime import CancellationToken
from alquimista.services import ExtractionService
from alquimista.ui.components import inform
from alquimista.ui.i18n import LanguageManager
from alquimista.ui.main_window import MainWindow
from alquimista.ui.pages.review_page import _toggle_log
from alquimista.ui.tree_models import display_timestamp


@pytest.fixture
def window(qtbot: Any, tmp_path: Path) -> MainWindow:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    manager = LanguageManager(QApplication.instance(), settings)
    manager.set_language("pt-BR", persist=False)
    created = MainWindow(language_manager=manager)
    yield created  # conftest closes MainWindows after clearing pending edits
    created.dirty = False


def _two_spaces(window: MainWindow) -> SourceConfig:
    source = SourceConfig(
        id="wiki", name="Wiki", source_type="confluence_rest", base_url="https://wiki.example.com",
        space_key="A", connector_options={"source_url": "https://wiki.example.com/spaces/A"},
    )
    window.project.sources = [source]
    window._refresh_source_widgets()
    pages = [{"id": f"a{n}", "title": f"Página {n}", "_container_id": "A", "ancestors": []} for n in range(3)]
    window.trees[source.id] = {
        "root": {"id": "all", "title": "Espaços"},
        "containers": [{"id": "A", "name": "Suporte"}, {"id": "B", "name": "Produto"}],
        "pages_by_container": {"A": pages},
        "pages": pages,
    }
    window._show_page("selection")
    window._refresh_selection_home()
    return source


def _space_row(window: MainWindow, container_id: str) -> int:
    table = window.selection_spaces_table
    return next(row for row in range(table.rowCount()) if table.item(row, 1).data(Qt.ItemDataRole.UserRole) == container_id)


def test_whole_space_checkbox_selects_and_clears_every_page(window: MainWindow) -> None:
    source = _two_spaces(window)
    table = window.selection_spaces_table

    table.item(_space_row(window, "A"), 0).setCheckState(Qt.CheckState.Checked)
    assert len(window.project.selected_keys_for(source.id)) == 3
    assert "3 páginas selecionadas em 1 de 2 espaços" in window.selection_total.text()

    table.item(_space_row(window, "A"), 0).setCheckState(Qt.CheckState.Unchecked)
    assert not window.project.selected_keys_for(source.id)


def test_whole_space_loads_an_unopened_space_first(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _two_spaces(window)

    def fake_load(src: SourceConfig, container_id: str, *, on_loaded: Any = None, **_kwargs: Any) -> None:
        loaded = [{"id": "b1", "title": "Planos", "_container_id": "B", "ancestors": []}]
        window.trees[src.id]["pages_by_container"][container_id] = loaded
        window.trees[src.id]["pages"] = window.trees[src.id]["pages"] + loaded
        on_loaded()

    monkeypatch.setattr(window, "_load_container_for_source", fake_load)
    window.selection_spaces_table.item(_space_row(window, "B"), 0).setCheckState(Qt.CheckState.Checked)

    assert window.project.selected_keys_for(source.id) == {"wiki:B:b1"}


def test_dates_in_the_tree_are_readable() -> None:
    assert display_timestamp("2026-09-01T10:00:00") == "01/09/2026 10:00"
    assert display_timestamp("") == ""
    assert display_timestamp("ontem") == "ontem"


def test_informational_messages_become_a_banner_with_an_action(window: MainWindow) -> None:
    clicked: list[bool] = []
    window.notify("Pronto.", "success", action=("Abrir", lambda: clicked.append(True)))
    assert window.banner.isVisibleTo(window) and window.banner_label.text() == "Pronto."
    window.banner_action.click()
    assert clicked == [True] and not window.banner.isVisibleTo(window)

    inform(window, "Título", "Sem pop-up.")
    assert window.banner_label.text() == "Sem pop-up."


def test_sidebar_collapses_on_narrow_windows_unless_the_user_chose(window: MainWindow) -> None:
    window.show()
    window.resize(1100, 760)
    QApplication.processEvents()
    assert window.sidebar.width() == 72 and window.nav_buttons["sources"].text() == ""

    window.resize(1400, 860)
    QApplication.processEvents()
    assert window.sidebar.width() == 235 and window.nav_buttons["sources"].text() == "Fontes"

    window._toggle_sidebar()
    window.resize(1500, 900)
    QApplication.processEvents()
    assert window.sidebar.width() == 72  # manual choice wins


def test_dropping_a_url_on_the_window_adds_the_source(window: MainWindow) -> None:
    mime = QMimeData()
    mime.setUrls([QUrl("https://docs.example.com/display/DOC/Manual")])
    event = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)

    window.dropEvent(event)

    assert window.project.sources[0].source_type == "confluence_rest"
    assert window.stack.currentWidget() is window.pages["sources"]


def test_sample_project_extracts_without_credentials(
    window: MainWindow, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))

    window.open_example_project()

    project = window.project
    assert project.sources[0].source_type == "local_files"
    assert len(project.selections) == 6
    runtimes = window._prepare_runtimes(project, CancellationToken(), lambda _message: None)
    report = ExtractionService(project, runtimes, tmp_path).run()
    assert report["counters"]["new"] == 6
    assert list(Path(project.output_dir).rglob("Trocas*.md"))


def test_real_page_preview_replaces_the_sample(window: MainWindow, monkeypatch: pytest.MonkeyPatch) -> None:
    source = _two_spaces(window)

    class Connector:
        def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
            return KnowledgeDocument(
                id=document_id, container_id="A", title="Política real", content="Texto da página real.",
                source_type="confluence_rest",
            )

        def close(self) -> None:
            pass

    monkeypatch.setattr(window.connector_registry, "create", lambda *args, **kwargs: Connector())
    monkeypatch.setattr(window, "_start_worker", lambda work, done: done(work(CancellationToken(), lambda *a: None, print)))

    window._preview_real_page(source, "A", "a1", "Política real")

    assert window.format_tabs.currentWidget() is window.pages["markdown"]
    assert "Texto da página real." in window.preview_after.toPlainText()
    assert "Política real" in window.preview_source_label.text()
    window._clear_real_preview()
    assert "Texto da página real." not in window.preview_after.toPlainText()


def test_settings_scroll_and_theme_is_remembered(window: MainWindow) -> None:
    scroll = next(area for area in window.pages["settings"].findChildren(QScrollArea))
    assert scroll.widget().isAncestorOf(window.timeout_spin)

    window.theme_combo.setCurrentIndex(window.theme_combo.findData("dark"))
    assert window._theme_preference() == "dark"


def test_run_log_can_be_shown(window: MainWindow) -> None:
    window._show_page("extraction")
    window.show()
    assert not window.log_text.isVisible()
    _toggle_log(window)
    assert window.log_text.isVisible() and "Ocultar" in window.log_toggle.text()
