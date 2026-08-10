from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QTextEdit,
    QWidget,
)

from ..components import button, card, page_header


def build_extraction_page(window: Any) -> QWidget:
    page, layout = page_header(
        "Extração e atualização",
        "Revise o resumo e acompanhe cada página sem congelar a interface.",
        "⚙",
    )
    summary, summary_layout = card()
    window.extraction_summary = QLabel()
    window.extraction_summary.setWordWrap(True)
    summary_layout.addWidget(window.extraction_summary)
    layout.addWidget(summary)
    window.progress = QProgressBar()
    window.progress.setRange(0, 100)
    layout.addWidget(window.progress)
    window.progress_label = QLabel("Pronto para executar.")
    layout.addWidget(window.progress_label)
    window.cancel_button = button("Cancelar operação", window.cancel_operation, danger=True)
    window.cancel_button.setEnabled(False)
    layout.addWidget(window.cancel_button)
    operation_card, operation_layout = card()
    operation_layout.addWidget(QLabel("O que deseja fazer agora?"))
    window.execution_mode = QComboBox()
    window.execution_mode.setAccessibleName("Tipo de operação")
    window.execution_mode.addItem("Extrair e consolidar", "complete")
    window.execution_mode.addItem("Somente extrair páginas", "extract")
    window.execution_mode.addItem("Somente consolidar arquivos já extraídos", "consolidate")
    window.execution_mode.setToolTip(
        "Escolha uma operação sem abrir outro programa. A opção recomendada é extrair e consolidar."
    )
    operation_layout.addWidget(window.execution_mode)
    window.execution_mode_help = QLabel(
        "Extrair e consolidar busca as páginas selecionadas e depois cria os pacotes. "
        "Somente consolidar usa o manifesto e os arquivos já extraídos."
    )
    window.execution_mode_help.setObjectName("subtitle")
    window.execution_mode_help.setWordWrap(True)
    operation_layout.addWidget(window.execution_mode_help)
    layout.addWidget(operation_card)
    actions = QHBoxLayout()
    actions.addWidget(button("▶ Executar operação escolhida", window.execute_selected_operation, primary=True))
    window.cancel_button = button("⏹ Cancelar", window.cancel_operation, danger=True)
    window.cancel_button.setEnabled(False)
    actions.addWidget(window.cancel_button)
    actions.addWidget(button("🔁 Repetir falhas", window.retry_failures))
    actions.addStretch()
    layout.addLayout(actions)
    window.log_text = QTextEdit()
    window.log_text.setReadOnly(True)
    window.log_text.setPlaceholderText("Os eventos da execução aparecerão aqui.")
    layout.addWidget(window.log_text, 1)
    return page

