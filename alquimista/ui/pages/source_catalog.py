"""Platform catalog (categorized connector cards) shown inside "Adicionar fonte"."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QGridLayout,
    QHBoxLayout,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..components import SourceCard, card
from ..i18n import translate_text


def _grid_position(index: int, total: int, *, cards_per_row: int = 3) -> tuple[int, int, int]:
    """Center incomplete rows in a grid where every card spans two columns."""
    row, index_in_row = divmod(index, cards_per_row)
    row_start = row * cards_per_row
    items_in_row = min(cards_per_row, total - row_start)
    span = 2
    grid_columns = cards_per_row * span
    offset = (grid_columns - items_in_row * span) // 2
    return row, offset + index_in_row * span, span


CATEGORIES = [
    ("all", "Todas"),
    ("knowledge_base", "Bases de Conhecimento"),
    ("customer_support", "Atendimento / Suporte"),
    ("developer", "Desenvolvedores"),
    ("cms", "CMS && Headless"),  # "&&": a single "&" is a Qt mnemonic and disappears
    ("web", "Web"),
    ("files", "Arquivos Locais"),
]


def build_source_catalog(window: Any) -> QWidget:
    """Category filter plus a scrollable grid of platform cards.

    Clicking a card calls ``window._source_card_clicked(source_type)``.
    """
    page = QWidget()
    main_layout = QVBoxLayout(page)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(10)

    # Category Filter Bar
    filter_bar = QHBoxLayout()
    filter_bar.setAlignment(Qt.AlignmentFlag.AlignCenter)
    filter_bar.setSpacing(6)

    category_group = QButtonGroup(page)
    category_group.setExclusive(True)

    grid_container = QWidget()
    source_grid = QGridLayout(grid_container)
    source_grid.setHorizontalSpacing(16)
    source_grid.setVerticalSpacing(16)
    source_grid.setContentsMargins(10, 10, 10, 10)
    for column in range(6):
        source_grid.setColumnStretch(column, 1)

    def refresh_cards(selected_category: str) -> None:
        # Clear current grid
        while source_grid.count():
            item = source_grid.takeAt(0)
            widget = item.widget() if item else None
            if widget:
                widget.setParent(None)

        filtered = [
            d
            for d in window.connector_registry.all()
            if d.card.visible and (selected_category == "all" or d.category == selected_category or d.card.category == selected_category)
        ]
        sorted_descriptors = sorted(filtered, key=lambda d: (d.card.order, d.source_type))

        for index, descriptor in enumerate(sorted_descriptors):
            spec = descriptor.card
            card_widget = SourceCard(
                descriptor.source_type,
                translate_text(spec.title or descriptor.display_name),
                translate_text(spec.description),
                spec.icon,
                spec.accent,
            )
            card_widget.clicked.connect(window._source_card_clicked)
            row, col, col_span = _grid_position(index, len(sorted_descriptors))
            source_grid.addWidget(card_widget, row, col, 1, col_span)

    for cat_id, cat_name in CATEGORIES:
        btn = QPushButton(cat_name)
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton { border: 1px solid #334155; border-radius: 14px; padding: 5px 12px; background: #1E293B; color: #94A3B8; font-size: 9pt; font-weight: 600; }"
            "QPushButton:checked { background: #3B82F6; color: #FFFFFF; border-color: #3B82F6; }"
            "QPushButton:hover:!checked { background: #334155; color: #F1F5F9; }"
        )
        if cat_id == "all":
            btn.setChecked(True)
        btn.clicked.connect(lambda _checked=False, c=cat_id: refresh_cards(c))
        category_group.addButton(btn)
        filter_bar.addWidget(btn)

    main_layout.addLayout(filter_bar)

    # Scrollable panel for cards
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll_area.setStyleSheet("background: transparent;")
    scroll_area.setWidget(grid_container)

    source_panel, source_layout = card()
    source_panel.setObjectName("sourcePanel")
    source_layout.setContentsMargins(12, 12, 12, 12)
    source_layout.addWidget(scroll_area)

    main_layout.addWidget(source_panel, 1)

    # Initial population
    refresh_cards("all")
    return page
