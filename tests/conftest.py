import os

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def reset_ui_language_preference() -> None:
    """Keep direct MainWindow tests deterministic regardless of user settings."""
    from alquimista.ui.i18n import create_settings

    settings = create_settings()
    settings.remove("preferences/language")
    settings.sync()


@pytest.fixture(autouse=True)
def cleanup_main_windows() -> None:
    """Release MainWindow widget trees after each Qt test."""
    yield

    app = QApplication.instance()
    if app is None:
        return
    for widget in list(app.topLevelWidgets()):
        if (
            widget.__class__.__name__ != "MainWindow"
            or widget.__class__.__module__ != "alquimista.ui.main_window"
        ):
            continue
        widget.dirty = False
        widget.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        widget.close()
        widget.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
