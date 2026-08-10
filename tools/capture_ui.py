"""Render deterministic UI screenshots for documentation.

This utility does not access Confluence or user data.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication

from alquimista.ui.main_window import MainWindow
from alquimista.ui.theme import apply_theme


def main() -> int:
    destination = Path("docs/screenshots")
    destination.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication(sys.argv)
    apply_theme(app, "dark")
    window = MainWindow("complete")
    window.resize(1366, 768)
    window.show()
    app.processEvents()
    source = window.project.sources[0]
    sample_tree = {
        "root": {"id": "100", "title": "Manual do Produto"},
        "pages": [
            {
                "id": "10",
                "title": "Como configurar uma venda",
                "type": "page",
                "ancestors": [
                    {"id": "100", "title": "Manual do Produto"},
                    {"id": "200", "title": "Vendas"},
                ],
                "version": {"number": 7, "when": "2026-07-24T12:30:00-03:00"},
            },
            {
                "id": "11",
                "title": "Emissão de nota fiscal",
                "type": "page",
                "ancestors": [
                    {"id": "100", "title": "Manual do Produto"},
                    {"id": "200", "title": "Vendas"},
                ],
                "version": {"number": 3, "when": "2026-06-18T09:00:00-03:00"},
            },
        ],
    }
    source.selected_page_ids = ["10"]
    window.trees[source.id] = sample_tree
    window._populate_page_tree(source, sample_tree)
    window._populate_selection_tree(source, sample_tree)
    for page, filename in (
        ("dashboard", "dashboard.png"),
        ("sources", "sources.png"),
        ("connection", "connection.png"),
        ("pages", "pages.png"),
        ("selection", "selection.png"),
        ("markdown", "markdown.png"),
        ("consolidation", "consolidation.png"),
        ("output", "output.png"),
        ("review", "review.png"),
    ):
        window._show_page(page)
        app.processEvents()
        if not window.grab().save(str(destination / filename), "PNG"):
            raise RuntimeError(f"Falha ao salvar {filename}")
    window.dirty = False
    window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
