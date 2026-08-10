"""Page composition registry for the main window.

Keeping the route-to-builder mapping outside ``MainWindow`` makes page
composition explicit and gives the future page widgets a stable seam without
changing their current construction methods yet.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtWidgets import QWidget


def page_builders(window: Any) -> dict[str, Callable[[], QWidget]]:
    return {        "dashboard": window._dashboard_page,
        "sources": window._sources_page,
        "connection": window._connection_page,
        "pages": window._selection_page,
        "selection": window._selection_page,
        "markdown": window._markdown_page,
        "consolidation": window._consolidation_page,
        "extraction": window._review_page,
        "review": window._review_page,
        "output": window._review_page,
        "results": window._results_page,
        "settings": window._settings_page,
    }
