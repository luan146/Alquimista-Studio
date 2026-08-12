from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QComboBox, QLabel, QWidget

from alquimista.ui.i18n import (
    LanguageManager,
    normalize_language,
    retranslate_widget_tree,
    system_language,
)
from alquimista.ui.main_window import MainWindow


def test_normalize_language_and_fallback() -> None:
    assert normalize_language("pt_BR") == "pt-BR"
    assert normalize_language("en-US") == "en"
    assert normalize_language("es_ES") == "es"
    assert normalize_language("system") is None
    assert normalize_language("fr") is None
    assert system_language() in {"pt-BR", "en", "es"}


def test_qt_catalogs_translate_supported_languages(qapp: QApplication, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    manager = LanguageManager(qapp, settings)

    assert manager.set_language("en", persist=False) == "en"
    assert manager.translate("Fontes") == "Sources"
    assert manager.set_language("es", persist=False) == "es"
    assert manager.translate("Fontes") == "Fuentes"
    assert manager.set_language("pt-BR", persist=False) == "pt-BR"
    assert manager.translate("Fontes") == "Fontes"


def test_widget_tree_retranslation_preserves_combo_data(
    qapp: QApplication, tmp_path: Path
) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    manager = LanguageManager(qapp, settings)
    manager.set_language("en", persist=False)
    root = QWidget()
    label = QLabel("Fontes", root)
    combo = QComboBox(root)
    combo.addItem("Fontes", "sources")
    retranslate_widget_tree(root)

    assert label.text() == "Sources"
    assert combo.itemText(0) == "Sources"
    assert combo.itemData(0) == "sources"


def test_dynamic_feedback_messages_translate_with_placeholders(
    qapp: QApplication, tmp_path: Path
) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    manager = LanguageManager(qapp, settings)
    manager.set_language("en", persist=False)

    assert manager.translate("Operação concluída.") == "Operation completed."
    assert (
        manager.translate("{count} páginas carregadas em {name}.").format(
            count=3, name="Docs"
        )
        == "3 pages loaded in Docs."
    )

    manager.set_language("es", persist=False)
    assert manager.translate("Operação concluída.") == "Operación completada."


def test_main_window_switches_major_pages_without_changing_internal_ids(
    qapp: QApplication, tmp_path: Path
) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    manager = LanguageManager(qapp, settings)
    manager.set_language("en", persist=False)
    window = MainWindow(language_manager=manager)

    assert window.nav_buttons["sources"].text() == "Sources"
    dashboard_title = next(
        label for label in window.pages["dashboard"].findChildren(QLabel)
        if label.objectName() == "pageTitle"
    )
    assert dashboard_title.text() == "Choose your knowledge source"
    assert window.selection_filter.itemData(0) == "all"
    assert window.selection_filter.itemText(0) == "📋 All pages"

    manager.set_language("es", persist=False)
    assert window.nav_buttons["sources"].text() == "Fuentes"
    assert window.selection_filter.itemText(0) == "📋 Todas las páginas"
    window.close()


def test_main_window_retranslates_dashboard_cards_after_pt_br_to_english(
    qapp: QApplication, tmp_path: Path
) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    manager = LanguageManager(qapp, settings)
    manager.set_language("pt-BR", persist=False)
    window = MainWindow(language_manager=manager)

    dashboard = window.pages["dashboard"]
    assert any(
        "Selecione a origem do conhecimento que você deseja usar." in label.text()
        for label in dashboard.findChildren(QLabel)
    )

    manager.set_language("en", persist=False)

    assert any(
        "Select the knowledge source you want to use." in label.text()
        for label in dashboard.findChildren(QLabel)
    )
    assert any(
        label.text() == "Connect and extract Zendesk Guide articles,\ntickets and solutions."
        for label in dashboard.findChildren(QLabel)
    )
    assert "Your connection is secure" in window.dashboard_status.text()
    window._show_page("sources")
    assert (
        window.source_url_input.placeholderText()
        == "Paste the Confluence, Notion, SharePoint, GitBook or Zendesk URL here"
    )
    assert (
        "Add page URLs so ALQuimista can extract and consolidate information automatically."
        in window.sources_empty_label.text()
    )
    window.close()
