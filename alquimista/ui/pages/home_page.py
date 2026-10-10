"""Início: where the project stands and what to do next (refreshed by ``_refresh_home``)."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QVBoxLayout,
    QWidget,
)

from ..components import button, card, metric_card, page_header


def build_home_page(window: Any) -> QWidget:
    page, layout = page_header(
        "Início",
        "Situação do projeto e o próximo passo.",
        "🧭",
    )

    # Project without sources: one clear way forward.
    window.home_empty, empty_layout = card()
    empty_title = QLabel("Comece adicionando uma fonte")
    empty_title.setObjectName("pageTitle")
    empty_layout.addWidget(empty_title)
    empty_text = QLabel(
        "Cole a URL de um espaço do Confluence, de uma página do Notion, de um site do "
        "SharePoint ou escolha uma pasta do computador. Depois você conecta, escolhe as "
        "páginas e executa."
    )
    empty_text.setObjectName("subtitle")
    empty_text.setWordWrap(True)
    empty_layout.addWidget(empty_text)
    empty_actions = QHBoxLayout()
    empty_actions.addWidget(button("＋ Adicionar fonte", window.open_add_source_dialog, primary=True))
    empty_actions.addWidget(button("📂 Abrir projeto", window.open_project))
    empty_actions.addStretch()
    empty_layout.addLayout(empty_actions)
    layout.addWidget(window.home_empty)

    # Project with sources: status at a glance and a single "continue" action.
    window.home_overview = QWidget()
    overview = QVBoxLayout(window.home_overview)
    overview.setContentsMargins(0, 0, 0, 0)
    overview.setSpacing(12)
    metrics = QGridLayout()
    metrics.setSpacing(12)
    window.home_metrics = {}
    for column, (key, title) in enumerate(
        [
            ("sources", "Fontes"),
            ("selection", "Seleção"),
            ("last_run", "Última execução"),
            ("schedule", "Sincronização agendada"),
        ]
    ):
        frame, value, detail = metric_card(title, "—", " ")
        detail.setWordWrap(True)
        window.home_metrics[key] = (value, detail)
        metrics.addWidget(frame, 0, column)
    overview.addLayout(metrics)

    next_card, next_layout = card()
    window.home_next_title = QLabel("")
    window.home_next_title.setStyleSheet("font-size: 13pt; font-weight: 700;")
    next_layout.addWidget(window.home_next_title)
    window.home_next_detail = QLabel("")
    window.home_next_detail.setObjectName("subtitle")
    window.home_next_detail.setWordWrap(True)
    next_layout.addWidget(window.home_next_detail)
    next_actions = QHBoxLayout()
    window.home_continue_button = button("Continuar →", window._continue_workflow, primary=True)
    next_actions.addWidget(window.home_continue_button)
    window.home_sync_button = button("🔄 Sincronizar agora", window.sync_project)
    window.home_sync_button.setToolTip("Baixa só o que mudou nas fontes desde a última execução")
    next_actions.addWidget(window.home_sync_button)
    next_actions.addStretch()
    next_layout.addLayout(next_actions)
    overview.addWidget(next_card)
    layout.addWidget(window.home_overview)

    recent_card, recent_layout = card()
    recent_header = QHBoxLayout()
    recent_title = QLabel("Projetos recentes")
    recent_title.setStyleSheet("font-weight: 700;")
    recent_header.addWidget(recent_title)
    recent_header.addStretch()
    recent_header.addWidget(button("➕ Novo projeto", window.new_project))
    recent_header.addWidget(button("📂 Abrir projeto", window.open_project))
    recent_layout.addLayout(recent_header)
    window.home_recent_list = QListWidget()
    window.home_recent_list.setAccessibleName("Projetos abertos recentemente")
    window.home_recent_list.itemActivated.connect(
        lambda item: window.open_project_path(item.data(Qt.ItemDataRole.UserRole))
    )
    recent_layout.addWidget(window.home_recent_list, 1)
    window.home_recent_empty = QLabel("Os projetos que você salvar ou abrir aparecem aqui.")
    window.home_recent_empty.setObjectName("subtitle")
    recent_layout.addWidget(window.home_recent_empty)
    layout.addWidget(recent_card, 1)
    return page
