"""Dashboard page construction, kept independent from navigation state."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from ..components import AlchemistIconAtlas, SourceCard, card
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


def build_dashboard_page(window: Any) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(26, 22, 26, 22)
    layout.setSpacing(8)
    hero_icon = QLabel()
    hero_icon.setObjectName("sourceHeroIcon")
    hero_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    hero_icon.setPixmap(AlchemistIconAtlas.pixmap(0, 86))
    layout.addWidget(hero_icon)
    title = QLabel("Escolha sua fonte de conhecimento")
    title.setObjectName("pageTitle")
    title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(title)
    subtitle = QLabel(
        "Selecione a origem do conhecimento que você deseja usar.\n"
        "Você poderá configurar os detalhes da conexão na próxima etapa."
    )
    subtitle.setObjectName("subtitle")
    subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
    subtitle.setWordWrap(True)
    layout.addWidget(subtitle)
    layout.addSpacing(10)
    source_panel, source_layout = card()
    source_panel.setObjectName("sourcePanel")
    source_layout.setContentsMargins(18, 18, 18, 18)
    source_grid = QGridLayout()
    source_grid.setHorizontalSpacing(16)
    source_grid.setVerticalSpacing(18)
    for column in range(6):
        source_grid.setColumnStretch(column, 1)
    descriptors = sorted(
        (
            descriptor
            for descriptor in window.connector_registry.all()
            if descriptor.card.visible
        ),
        key=lambda descriptor: (descriptor.card.order, descriptor.source_type),
    )
    for index, descriptor in enumerate(descriptors):
        spec = descriptor.card
        source_card = SourceCard(
            descriptor.source_type,
            translate_text(spec.title or descriptor.display_name),
            translate_text(spec.description),
            spec.icon,
            spec.accent,
        )
        source_card.clicked.connect(window._source_card_clicked)
        row, column, column_span = _grid_position(index, len(descriptors))
        source_grid.addWidget(source_card, row, column, 1, column_span)
    source_layout.addLayout(source_grid)
    layout.addWidget(source_panel, 1)
    window.dashboard_status = QLabel(
        "🔒  Sua conexão é segura. Nenhum dado é armazenado sem o seu consentimento."
    )
    window.dashboard_status.setObjectName("subtitle")
    window.dashboard_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(window.dashboard_status)
    return page
