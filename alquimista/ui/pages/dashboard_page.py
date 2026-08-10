"""Dashboard page construction, kept independent from navigation state."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from ..components import AlchemistIconAtlas, SourceCard, card


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
    sources = [
        ("zendesk_guide", "Zendesk", "Conecte e extraia artigos,\ntickets e soluções do Zendesk Guide.", 10, "#7FE4B5", 0),
        ("confluence_rest", "Confluence", "Acesse páginas, espaços\ne documentos do Atlassian Confluence.", 11, "#67B7FF", 2),
        ("notion_api", "Notion", "Importe páginas, bases de dados\ne conteúdos do Notion.", 12, "#B09AFF", 4),
        ("sharepoint_graph", "SharePoint", "Explore sites, bibliotecas e documentos\ndo Microsoft SharePoint.", 13, "#75E7BA", 1),
        ("gitbook_api", "GitBook", "Importe documentação e conteúdos\ndisponíveis na sua base do GitBook.", 14, "#B09AFF", 3),
    ]
    for row, (source_type, name, description, icon, accent, column) in enumerate(sources):
        source_card = SourceCard(source_type, name, description, icon, accent)
        source_card.clicked.connect(window._source_card_clicked)
        source_grid.addWidget(source_card, 0 if row < 3 else 1, column, 1, 2)
    source_layout.addLayout(source_grid)
    layout.addWidget(source_panel, 1)
    window.dashboard_status = QLabel(
        "🔒  Sua conexão é segura. Nenhum dado é armazenado sem o seu consentimento."
    )
    window.dashboard_status.setObjectName("subtitle")
    window.dashboard_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(window.dashboard_status)
    return page
