from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..components import button, card, metric_card, page_header


def build_results_page(window: Any) -> QWidget:
    page, layout = page_header(
        "Resultados e relatórios",
        "Resumo completo da execução, arquivos gerados e atalhos úteis.",
        "📊",
    )

    # 1. Cartões de Métricas da Execução Final
    metrics_layout = QHBoxLayout()
    metrics_layout.setSpacing(12)

    total_card, window.result_metric_total, _ = metric_card(
        "Páginas Processadas", "0", "Total analisado"
    )
    packages_card, window.result_metric_packages, _ = metric_card(
        "Pacotes Gerados", "0", "Arquivos Markdown"
    )
    time_card, window.result_metric_time, _ = metric_card(
        "Tempo Total", "0.0s", "Duração da operação"
    )
    failures_card, window.result_metric_failures, _ = metric_card(
        "Falhas / Revisões", "0", "Itens com atenção"
    )

    metrics_layout.addWidget(total_card)
    metrics_layout.addWidget(packages_card)
    metrics_layout.addWidget(time_card)
    metrics_layout.addWidget(failures_card)
    layout.addLayout(metrics_layout)

    # 2. Painel de Atalhos de Saída
    output_card, output_layout = card()
    output_layout.setContentsMargins(14, 10, 14, 10)
    output_row = QHBoxLayout()
    output_row.setSpacing(12)

    folder_info = QVBoxLayout()
    folder_info.setSpacing(2)
    folder_title = QLabel("Destino dos arquivos gerados")
    folder_title.setStyleSheet("font-weight: 700; font-size: 10pt;")
    folder_info.addWidget(folder_title)
    window.result_output_path_label = QLabel("Acesse os arquivos consolidados e avulsos na pasta de saída.")
    window.result_output_path_label.setObjectName("subtitle")
    window.result_output_path_label.setWordWrap(True)
    folder_info.addWidget(window.result_output_path_label)
    output_row.addLayout(folder_info, 1)

    output_row.addWidget(button("📁 Abrir pasta", window.open_output, primary=True))
    output_row.addWidget(button("Copiar caminho", window.copy_output_path))
    output_layout.addLayout(output_row)
    layout.addWidget(output_card)

    # 3. Card com o Relatório Completo
    report_card, report_layout = card()
    report_layout.setContentsMargins(14, 12, 14, 12)
    report_layout.setSpacing(8)

    report_header = QHBoxLayout()
    report_title = QLabel("Relatório de consolidação e manifesto")
    report_title.setStyleSheet("font-weight: 700; font-size: 10.5pt;")
    report_header.addWidget(report_title)
    report_header.addStretch()
    report_header.addWidget(button("📋 Copiar relatório", window.copy_report))
    report_header.addWidget(button("💾 Exportar", window.export_report))
    report_layout.addLayout(report_header)

    window.result_summary = QTextEdit()
    window.result_summary.setObjectName("logTerminal")
    window.result_summary.setReadOnly(True)
    window.result_summary.setPlaceholderText("✨ Execute uma operação para ver o relatório.")
    report_layout.addWidget(window.result_summary, 1)
    layout.addWidget(report_card, 1)

    # 4. Rodapé com Ações Técnicas
    actions = QHBoxLayout()
    actions.addWidget(button("🧾 Abrir manifesto", window.open_manifest))
    actions.addWidget(button("🛠 Abrir log técnico", window.open_log))
    actions.addStretch()
    actions.addWidget(button("← Voltar para Fontes", lambda: window._show_page("sources")))
    layout.addLayout(actions)

    return page
