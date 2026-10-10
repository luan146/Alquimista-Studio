"""Step 3 'Saída': Markdown format and package (consolidation) rules as two tabs."""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from .consolidation_page import build_consolidation_page
from .markdown_page import build_markdown_page


def build_format_page(window: Any) -> tuple[QWidget, QWidget, QWidget]:
    """Return the page plus its Markdown and Pacotes tabs (for page aliases)."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(20, 12, 20, 0)
    window.format_tabs = QTabWidget()
    window.format_tabs.setDocumentMode(True)
    markdown = build_markdown_page(window)
    packages = build_consolidation_page(window)
    window.format_tabs.addTab(markdown, "✍ Markdown")
    window.format_tabs.addTab(packages, "📦 Pacotes para IA")
    layout.addWidget(window.format_tabs)
    return page, markdown, packages
