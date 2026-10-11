"""Step 3 'Saída': Markdown format and package (consolidation) rules as two tabs."""
from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QHBoxLayout, QTabWidget, QVBoxLayout, QWidget

from ..components import SegmentedControl
from .consolidation_page import build_consolidation_page
from .markdown_page import build_markdown_page


def build_format_page(window: Any) -> tuple[QWidget, QWidget, QWidget]:
    """Return the page plus its Markdown and Pacotes tabs (for page aliases)."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(20, 14, 20, 0)
    window.format_tabs = QTabWidget()
    window.format_tabs.setDocumentMode(True)
    markdown = build_markdown_page(window)
    packages = build_consolidation_page(window)
    window.format_tabs.addTab(markdown, "Markdown")
    window.format_tabs.addTab(packages, "Pacotes para IA")
    # The pills replace the tab bar; the QTabWidget stays as the page-alias target.
    window.format_tabs.tabBar().setVisible(False)
    window.format_switch = SegmentedControl([("Markdown", 0), ("Pacotes para IA", 1)]).bind_stack(
        window.format_tabs
    )
    switch_row = QHBoxLayout()
    switch_row.setContentsMargins(8, 0, 0, 0)
    switch_row.addWidget(window.format_switch)
    switch_row.addStretch()
    layout.addLayout(switch_row)
    layout.addWidget(window.format_tabs)
    return page, markdown, packages
