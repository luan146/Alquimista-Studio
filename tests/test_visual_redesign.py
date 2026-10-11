"""Novo visual: ícones SVG, tema, peças novas e telas remontadas."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from PySide6.QtCore import QPoint, QSettings, Qt
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton, QStackedWidget, QWidget

from alquimista.models import MarkdownOptions, SourceConfig
from alquimista.ui.components import AlchemistIconAtlas, SegmentedControl, chip
from alquimista.ui.i18n import LanguageManager
from alquimista.ui.icons import (
    AUTH_ICONS,
    CONTROL_ICONS,
    EMOJI_ICONS,
    ICON_DIR,
    SYSTEM_ICONS,
    icon_path,
    svg_pixmap,
)
from alquimista.ui.main_window import MainWindow
from alquimista.ui.space_cards import SpaceCardDelegate
from alquimista.ui.theme import DARK, LIGHT, apply_theme, current_colors, stylesheet
from alquimista.ui.tree_models import relative_timestamp


def test_every_mapped_icon_has_an_svg_that_renders(qapp) -> None:
    names = {*SYSTEM_ICONS, *AUTH_ICONS, *EMOJI_ICONS.values(), "pagina_restrita", *CONTROL_ICONS}
    for name in names:
        assert icon_path(name).exists(), name
        assert not svg_pixmap(name, 24).isNull(), name


def test_old_atlas_indices_now_draw_the_svg_icons(qapp) -> None:
    assert AlchemistIconAtlas.pixmap(11, 32).cacheKey() == svg_pixmap("pasta", 32).cacheKey()
    assert AlchemistIconAtlas.auth_pixmap(7, 24).cacheKey() == svg_pixmap("sair", 24).cacheKey()
    assert not AlchemistIconAtlas.connector_icon(0, 24).isNull()  # plataformas continuam no atlas


def test_segmented_control_drives_and_follows_its_combo(qapp) -> None:
    combo = QComboBox()
    for label, value in (("Claro", "light"), ("Escuro", "dark")):
        combo.addItem(label, value)
    control = SegmentedControl([("Claro", "light"), ("Escuro", "dark")]).bind_combo(combo)
    assert control.value() == "light"
    control.buttons()[1].click()
    assert combo.currentData() == "dark"
    combo.setCurrentIndex(0)
    assert control.buttons()[0].isChecked()


def test_segmented_control_hides_options_disabled_in_the_combo(qapp) -> None:
    combo = QComboBox()
    combo.addItem("A", "a")
    combo.addItem("B", "b")
    combo.model().item(1).setEnabled(False)
    control = SegmentedControl([("A", "a"), ("B", "b")]).bind_combo(combo)
    control.sync_enabled_from(combo)
    assert control.buttons()[1].isHidden()


def test_segmented_control_switches_a_stack(qapp) -> None:
    stack = QStackedWidget()
    stack.addWidget(QWidget())
    stack.addWidget(QWidget())
    control = SegmentedControl([("Um", 0), ("Dois", 1)], vertical=True).bind_stack(stack)
    control.buttons()[1].click()
    assert stack.currentIndex() == 1


def test_both_themes_build_a_stylesheet_with_existing_control_images(qapp) -> None:
    for colors in (LIGHT, DARK):
        sheet = stylesheet(colors)
        assert colors["primary"] in sheet
        for name in ("controle_check_on", "controle_switch_on", "controle_seta_baixo", "controle_seta_cima"):
            assert (ICON_DIR / f"{name}.svg").as_posix() in sheet
    apply_theme(QApplication.instance(), "dark")
    assert current_colors() is DARK
    apply_theme(QApplication.instance(), "light")
    assert current_colors() is LIGHT


def test_chip_kind_is_a_style_property(qapp) -> None:
    label = chip("Inteiro", "accent")
    assert label.objectName() == "chip" and label.property("kind") == "accent"


@pytest.fixture
def window(qtbot: Any, tmp_path: Path) -> MainWindow:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    manager = LanguageManager(QApplication.instance(), settings)
    manager.set_language("pt-BR", persist=False)
    created = MainWindow(language_manager=manager)
    yield created
    created.dirty = False


def _spaces(window: MainWindow, count: int = 2) -> SourceConfig:
    source = SourceConfig(id="wiki", name="Wiki", source_type="confluence_rest", base_url="https://wiki.example.com",
                          space_key="A", connector_options={"source_url": "https://wiki.example.com/spaces/A"})
    window.project.sources = [source]
    window._refresh_source_widgets()
    pages = [{"id": f"a{n}", "title": f"Página {n}", "_container_id": "A", "ancestors": []} for n in range(3)]
    containers = [{"id": "A", "name": "Suporte"}, {"id": "B", "name": "Produto"}]
    containers += [{"id": f"X{n}", "name": f"Espaço {n}"} for n in range(count - 2)]
    window.trees[source.id] = {"root": {"id": "all", "title": "Espaços"}, "containers": containers,
                               "pages_by_container": {"A": pages}, "pages": pages}
    window._show_page("selection")
    window._refresh_selection_home()
    return source


def _card_center(window: MainWindow, container_id: str, *, pill: bool) -> Any:
    view = window.selection_spaces
    item = next(view.item(row) for row in range(view.count())
                if view.item(row).data(Qt.ItemDataRole.UserRole) == container_id)
    rect = view.visualItemRect(item)
    return (SpaceCardDelegate.pill_rect(rect) if pill else rect.adjusted(10, 40, -10, -10)).center()


def test_relative_dates() -> None:
    now = datetime(2026, 10, 10, 12, tzinfo=timezone.utc)  # noon UTC on both sides: same local day anywhere
    assert relative_timestamp("2026-10-10T12:00:00Z", now) == "hoje"
    assert relative_timestamp("2026-10-09T12:00:00Z", now) == "ontem"
    assert relative_timestamp("2026-10-07T12:00:00Z", now) == "há 3 dias"
    assert relative_timestamp("2026-09-01T12:00:00Z", now) == "há 1 mês"
    assert relative_timestamp("2026-08-01T12:00:00Z", now) == "há 2 meses"
    assert relative_timestamp("2025-09-05T12:00:00Z", now) == "há 1 ano"
    assert relative_timestamp("2024-01-01T12:00:00Z", now) == "há 2 anos"
    assert relative_timestamp("", now) == "" and relative_timestamp("ontem?", now) == "ontem?"


def test_whole_pill_click_marks_the_space(window: MainWindow, qtbot: Any) -> None:
    source = _spaces(window)
    window.show()
    QApplication.processEvents()
    qtbot.mouseClick(window.selection_spaces.viewport(), Qt.MouseButton.LeftButton,
                     pos=_card_center(window, "A", pill=True))
    assert len(window.project.selected_keys_for(source.id)) == 3
    assert window.selection_stack.currentIndex() == 0  # pill marks, it does not open


def test_whole_pill_click_marks_unloaded_space(window: MainWindow, qtbot: Any,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    source = _spaces(window)

    def fake_load(src: SourceConfig, container_id: str, *, on_loaded: Any = None, **_kwargs: Any) -> None:
        loaded = [{"id": "b1", "title": "Planos", "_container_id": "B", "ancestors": []}]
        window.trees[src.id]["pages_by_container"][container_id] = loaded
        window.trees[src.id]["pages"] = window.trees[src.id]["pages"] + loaded
        on_loaded()

    monkeypatch.setattr(window, "_load_container_for_source", fake_load)
    window.show()
    QApplication.processEvents()
    qtbot.mouseClick(window.selection_spaces.viewport(), Qt.MouseButton.LeftButton,
                     pos=_card_center(window, "B", pill=True))
    assert window.project.selected_keys_for(source.id) == {"wiki:B:b1"}


def test_clicking_the_card_body_opens_the_space(window: MainWindow, qtbot: Any) -> None:
    _spaces(window)
    window.show()
    QApplication.processEvents()
    qtbot.mouseClick(window.selection_spaces.viewport(), Qt.MouseButton.LeftButton,
                     pos=_card_center(window, "A", pill=False))
    assert window.selection_stack.currentIndex() == 1
    assert window.selection_space_title.text() == "Suporte"


def test_space_search_hides_cards_without_widgets(window: MainWindow) -> None:
    _spaces(window, count=300)
    assert window.selection_spaces.count() == 300
    assert not window.selection_spaces.findChildren(QPushButton)  # cards are painted, not widgets
    window.selection_space_search.setText("produto")
    visible = [window.selection_spaces.item(r).data(Qt.ItemDataRole.UserRole)
               for r in range(window.selection_spaces.count()) if not window.selection_spaces.item(r).isHidden()]
    assert visible == ["B"]


def test_space_card_colors_follow_theme(window: MainWindow) -> None:
    from alquimista.ui.space_cards import tile_colors
    apply_theme(QApplication.instance(), "light")
    light = tile_colors("Suporte")
    apply_theme(QApplication.instance(), "dark")
    dark = tile_colors("Suporte")
    apply_theme(QApplication.instance(), "light")
    assert light != dark and tile_colors("Suporte") == light  # stable per name, per theme


def test_selection_filter_pills_drive_the_hidden_combo(window: MainWindow) -> None:
    window.selection_filter_pills.buttons()[1].click()
    assert window.selection_filter.currentData() == "selected"


def test_relative_dates_count_days_on_the_local_clock() -> None:
    late = datetime(2026, 10, 9, 22, 30).astimezone()  # 22:30 local yesterday, whatever the zone
    now = datetime(2026, 10, 10, 9, 0).astimezone()
    assert relative_timestamp(late.astimezone(timezone.utc).isoformat(), now) == "ontem"


def test_space_key_marks_the_current_card(window: MainWindow, qtbot: Any) -> None:
    source = _spaces(window)
    view = window.selection_spaces
    view.setCurrentRow(next(r for r in range(view.count()) if view.item(r).data(Qt.ItemDataRole.UserRole) == "A"))
    qtbot.keyClick(view, Qt.Key.Key_Space)
    assert len(window.project.selected_keys_for(source.id)) == 3
    assert view.currentItem().data(Qt.ItemDataRole.UserRole) == "A"  # refresh keeps the keyboard position
    qtbot.keyClick(view, Qt.Key.Key_Space)
    assert not window.project.selected_keys_for(source.id)


def test_output_switch_and_tabs_stay_in_sync(window: MainWindow) -> None:
    window._show_page("consolidation")
    assert window.format_switch.value() == 1
    window.format_switch.buttons()[0].click()
    assert window.format_tabs.currentIndex() == 0
    assert window.format_tabs.tabBar().isHidden()


def test_markdown_options_are_switch_rows_that_toggle_on_click(window: MainWindow, qtbot: Any) -> None:
    check = window.md_controls["include_title"]
    assert check.property("switch") is True
    row = check.parentWidget()
    before = check.isChecked()
    window._show_page("markdown")
    window.show()
    QApplication.processEvents()
    qtbot.mouseClick(row, Qt.MouseButton.LeftButton, pos=row.rect().topLeft() + QPoint(8, 8))
    assert check.isChecked() is not before


def test_preview_opens_in_visual_mode_and_presets_mark_the_active_card(window: MainWindow) -> None:
    assert window.preview_mode.currentData() == "reading"
    window.preview_mode_pills.buttons()[1].click()
    assert window.preview_mode.currentData() == "code"
    window.preset_cards["rag"].click()
    assert window.preset_cards["rag"].isChecked() and not window.preset_cards["minimum"].isChecked()


def _checked_presets(window: MainWindow) -> list[str]:
    return [name for name, card in window.preset_cards.items() if card.isChecked()]


def test_preset_card_follows_the_loaded_project_options(window: MainWindow) -> None:
    assert _checked_presets(window) == ["recommended"]
    window.project.markdown = MarkdownOptions.preset("rag")
    window._load_markdown_controls()
    assert _checked_presets(window) == ["rag"]


def test_preset_card_clears_when_a_switch_is_flipped(window: MainWindow) -> None:
    window.preset_cards["minimum"].click()
    assert _checked_presets(window) == ["minimum"]
    check = window.md_controls["include_title"]
    check.setChecked(not check.isChecked())
    assert _checked_presets(window) == []


def test_settings_menu_switches_sections_and_theme_tiles_save_the_theme(window: MainWindow) -> None:
    window._show_page("settings")
    window.settings_menu.buttons()[2].click()
    assert window.settings_stack.currentWidget().isAncestorOf(window.timeout_spin)
    window.theme_tiles.buttons()[1].click()  # Escuro
    assert window._theme_preference() == "dark"
    window.ui_scale_pills.buttons()[-1].click()
    assert window._ui_scale_preference() == 1.5
