import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def reset_ui_language_preference() -> None:
    """Keep direct MainWindow tests deterministic regardless of user settings."""
    from alquimista.ui.i18n import create_settings

    settings = create_settings()
    settings.remove("preferences/language")
    settings.sync()
