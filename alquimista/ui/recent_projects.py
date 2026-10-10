"""Most-recently-used project files, kept in the user's QSettings."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings

_KEY = "projects/recent"
_LIMIT = 8


def recent_projects(settings: QSettings) -> list[Path]:
    """Existing project files, newest first."""
    raw: Any = settings.value(_KEY, [])
    # QSettings returns a bare string when the list has a single item.
    values = [raw] if isinstance(raw, str) else list(raw or [])
    return [Path(value) for value in values if value and Path(value).is_file()]


def remember_project(settings: QSettings, path: Path) -> None:
    resolved = str(path.resolve())
    others = [str(item) for item in recent_projects(settings) if str(item) != resolved]
    settings.setValue(_KEY, [resolved, *others][:_LIMIT])
    settings.sync()
