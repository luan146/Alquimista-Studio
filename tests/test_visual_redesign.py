"""Novo visual: ícones SVG, tema, peças novas e telas remontadas."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication, QComboBox, QStackedWidget, QWidget

from alquimista.ui.components import AlchemistIconAtlas, SegmentedControl, chip
from alquimista.ui.icons import (
    AUTH_ICONS,
    CONTROL_ICONS,
    EMOJI_ICONS,
    ICON_DIR,
    SYSTEM_ICONS,
    icon_path,
    svg_pixmap,
)
from alquimista.ui.theme import DARK, LIGHT, apply_theme, current_colors, stylesheet


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
        for name in ("controle_check_on", "controle_switch_on"):
            assert (ICON_DIR / f"{name}.svg").as_posix() in sheet
    apply_theme(QApplication.instance(), "dark")
    assert current_colors() is DARK
    apply_theme(QApplication.instance(), "light")
    assert current_colors() is LIGHT


def test_chip_kind_is_a_style_property(qapp) -> None:
    label = chip("Inteiro", "accent")
    assert label.objectName() == "chip" and label.property("kind") == "accent"
