from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..components import button, card, metric_card, page_header


def build_extraction_page(window: Any) -> QWidget:
    page, layout = page_header(
        "Extração e execução",
        "Acompanhe visualmente cada etapa da extração, conversão para Markdown e consolidação.",
        "⚙",
    )

    # 1. Painel de Métricas em Tempo Real
    metrics_layout = QHBoxLayout()
    metrics_layout.setSpacing(12)

    progress_card, window.metric_progress_value, _ = metric_card(
        "Progresso Geral", "0%", "0 de 0 processadas"
    )
    status_card, window.metric_status_value, _ = metric_card(
        "Status", "Pronto", "Aguardando início"
    )
    window.metric_status_value.setStyleSheet("font-size: 14pt;")
    success_card, window.metric_success_value, _ = metric_card(
        "Páginas Extraídas", "0", "Convertidas com sucesso"
    )
    failures_card, window.metric_failures_value, _ = metric_card(
        "Falhas / Avisos", "0", "Erros registrados"
    )

    metrics_layout.addWidget(progress_card)
    metrics_layout.addWidget(status_card)
    metrics_layout.addWidget(success_card)
    metrics_layout.addWidget(failures_card)
    layout.addLayout(metrics_layout)

    # 2. Card de Status e Resumo
    summary_card, summary_layout = card()
    summary_layout.setContentsMargins(14, 12, 14, 12)
    summary_layout.setSpacing(8)

    window.extraction_summary = QLabel("Revise suas configurações e seleções antes de iniciar a extração.")
    window.extraction_summary.setObjectName("subtitle")
    window.extraction_summary.setWordWrap(True)
    summary_layout.addWidget(window.extraction_summary)

    # Barra de progresso com rótulo
    progress_box = QVBoxLayout()
    progress_box.setSpacing(6)
    window.progress_label = QLabel("Pronto para executar.")
    window.progress_label.setStyleSheet("font-weight: 600; font-size: 10pt;")
    progress_box.addWidget(window.progress_label)

    window.progress = QProgressBar()
    window.progress.setRange(0, 100)
    window.progress.setValue(0)
    window.progress.setTextVisible(True)
    progress_box.addWidget(window.progress)
    summary_layout.addLayout(progress_box)
    layout.addWidget(summary_card)

    # 3. Card de Controle de Operação e Ações
    ctrl_card, ctrl_layout = card()
    ctrl_layout.setContentsMargins(14, 12, 14, 12)
    ctrl_layout.setSpacing(10)

    ctrl_header = QHBoxLayout()
    ctrl_title = QLabel("Configuração de execução")
    ctrl_title.setStyleSheet("font-size: 11pt; font-weight: 700;")
    ctrl_header.addWidget(ctrl_title)
    ctrl_header.addStretch()
    ctrl_layout.addLayout(ctrl_header)

    mode_row = QHBoxLayout()
    mode_row.setSpacing(10)
    mode_row.addWidget(QLabel("Operação:"))
    window.execution_mode = QComboBox()
    window.execution_mode.setAccessibleName("Tipo de operação")
    window.execution_mode.addItem("Extrair e consolidar", "complete")
    window.execution_mode.addItem("Somente extrair páginas", "extract")
    window.execution_mode.addItem("Somente consolidar arquivos já extraídos", "consolidate")
    window.execution_mode.currentIndexChanged.connect(window._update_execution_mode_help)
    mode_row.addWidget(window.execution_mode, 2)

    window.execution_mode_help = QLabel(
        "Extrair e consolidar busca as páginas selecionadas e depois cria os pacotes."
    )
    window.execution_mode_help.setObjectName("subtitle")
    window.execution_mode_help.setWordWrap(True)
    mode_row.addWidget(window.execution_mode_help, 3)
    ctrl_layout.addLayout(mode_row)

    actions = QHBoxLayout()
    actions.setSpacing(10)
    actions.addWidget(
        button("🚀 Executar operação escolhida", window.execute_selected_operation, primary=True)
    )
    window.cancel_button = button("⏹ Cancelar", window.cancel_operation, danger=True)
    window.cancel_button.setEnabled(False)
    actions.addWidget(window.cancel_button)
    actions.addWidget(button("🔁 Repetir falhas", window.retry_failures))
    actions.addStretch()
    ctrl_layout.addLayout(actions)
    layout.addWidget(ctrl_card)

    # 4. Console de Eventos e Logs em Tempo Real
    log_card, log_layout = card()
    log_layout.setContentsMargins(14, 12, 14, 12)
    log_layout.setSpacing(8)

    log_header = QHBoxLayout()
    log_title = QLabel("Registro de eventos e log em tempo real")
    log_title.setStyleSheet("font-weight: 700; font-size: 10pt;")
    log_header.addWidget(log_title)
    log_header.addStretch()

    def _clear_log() -> None:
        window.log_text.clear()

    log_header.addWidget(button("Limpar log", _clear_log))
    log_layout.addLayout(log_header)

    window.log_text = QTextEdit()
    window.log_text.setObjectName("logTerminal")
    window.log_text.setReadOnly(True)
    window.log_text.setPlaceholderText("Os eventos da execução aparecerão aqui em tempo real...")
    log_layout.addWidget(window.log_text, 1)
    layout.addWidget(log_card, 1)

    return page
