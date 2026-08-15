from __future__ import annotations

from PySide6.QtWidgets import QApplication

from alquimista.ui.components import SourceCard, _LegacySourceCard
from alquimista.ui.i18n import create_settings
from alquimista.ui.main_window import MainWindow


def test_visual_profile_switches_style_and_persists(qtbot) -> None:
    settings = create_settings()
    key = "preferences/visual_profile"
    previous = settings.value(key)
    settings.remove(key)
    settings.sync()
    first = MainWindow()
    qtbot.addWidget(first)

    try:
        assert first.visual_profile == "atelier"
        assert first.visual_profile_combo.currentData() == "atelier"

        legacy_index = first.visual_profile_combo.findData("legacy")
        first.visual_profile_combo.setCurrentIndex(legacy_index)

        assert first.visual_profile == "legacy"
        assert settings.value(key) == "legacy"
        assert "#126E75" in QApplication.instance().styleSheet()
        assert "border-radius: 9px" in QApplication.instance().styleSheet()
        assert len(first.pages["dashboard"].findChildren(_LegacySourceCard)) == 28

        first.close()
        second = MainWindow()
        qtbot.addWidget(second)
        assert second.visual_profile == "legacy"
        assert second.visual_profile_combo.currentData() == "legacy"
        second.visual_profile_combo.setCurrentIndex(
            second.visual_profile_combo.findData("atelier")
        )
        assert second.visual_profile == "atelier"
        assert len(second.pages["dashboard"].findChildren(SourceCard)) == 28
        second.close()
    finally:
        if previous is None:
            settings.remove(key)
        else:
            settings.setValue(key, previous)
        settings.sync()
