import os

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def no_installed_tesseract(monkeypatch: pytest.MonkeyPatch) -> None:
    """Extraction tests must not download images just because Tesseract is installed."""
    from alquimista import image_text

    monkeypatch.setattr(image_text, "tesseract_path", lambda: None)


@pytest.fixture(autouse=True)
def silence_windows_notifications(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Unattended-sync tests must not pop real Windows notifications."""
    from alquimista import scheduler

    shown: list[tuple[str, str]] = []
    monkeypatch.setattr(scheduler, "notify", lambda title, text: shown.append((title, text)))
    return shown


@pytest.fixture(autouse=True)
def reset_ui_language_preference() -> None:
    """Keep direct MainWindow tests deterministic regardless of user settings."""
    from alquimista.ui.i18n import create_settings

    settings = create_settings()
    settings.remove("preferences/language")
    settings.sync()
    app = QApplication.instance()
    if app is not None:
        # A test that switched languages must not leak it into the next one.
        app.setProperty("_alquimista_language", "pt-BR")


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
