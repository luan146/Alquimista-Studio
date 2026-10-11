from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..components import button, card, metric_card, page_header


def _table(headers: list[str], name: str) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setAccessibleName(name)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    return table


def build_results_page(window: Any) -> QWidget:
    page, layout = page_header(
        "Resultados e relatórios",
        "Resumo completo da execução, arquivos gerados e atalhos úteis.",
        "📊",
    )

    # Nothing has run yet for this project.
    window.results_empty, empty_layout = card()
    empty_title = QLabel("Nenhuma execução ainda")
    empty_title.setObjectName("pageTitle")
    empty_layout.addWidget(empty_title)
    empty_text = QLabel(
        "Quando você executar a extração, o resumo, as falhas e o histórico aparecem aqui."
    )
    empty_text.setObjectName("subtitle")
    empty_text.setWordWrap(True)
    empty_layout.addWidget(empty_text)
    empty_layout.addWidget(
        button("🚀 Ir para Executar", lambda: window._show_page("extraction"), primary=True),
        0,
        Qt.AlignmentFlag.AlignLeft,
    )
    layout.addWidget(window.results_empty)

    window.results_body = QWidget()
    body = QVBoxLayout(window.results_body)
    body.setContentsMargins(0, 0, 0, 0)
    body.setSpacing(12)

    metrics_layout = QHBoxLayout()
    metrics_layout.setSpacing(12)
    total_card, window.result_metric_total, _ = metric_card("Páginas Processadas", "0", "Total analisado")
    packages_card, window.result_metric_packages, _ = metric_card("Pacotes Gerados", "0", "Arquivos Markdown")
    time_card, window.result_metric_time, _ = metric_card("Tempo Total", "0.0s", "Duração da operação")
    failures_card, window.result_metric_failures, _ = metric_card("Falhas / Revisões", "0", "Itens com atenção")
    for metric in (total_card, packages_card, time_card, failures_card):
        metrics_layout.addWidget(metric)
    body.addLayout(metrics_layout)

    output_card, output_layout = card()
    output_layout.setContentsMargins(14, 10, 14, 10)
    output_row = QHBoxLayout()
    folder_info = QVBoxLayout()
    folder_info.setSpacing(2)
    folder_title = QLabel("Destino dos arquivos gerados")
    folder_title.setObjectName("sectionTitle")
    folder_info.addWidget(folder_title)
    window.result_output_path_label = QLabel("Acesse os arquivos consolidados e avulsos na pasta de saída.")
    window.result_output_path_label.setObjectName("subtitle")
    window.result_output_path_label.setWordWrap(True)
    folder_info.addWidget(window.result_output_path_label)
    output_row.addLayout(folder_info, 1)
    output_row.addWidget(button("📁 Abrir pasta", window.open_output, primary=True))
    output_row.addWidget(button("Copiar caminho", window.copy_output_path))
    output_row.addWidget(button("🧾 Abrir manifesto", window.open_manifest))
    output_row.addWidget(button("🛠 Abrir log técnico", window.open_log))
    output_layout.addLayout(output_row)
    body.addWidget(output_card)

    window.results_tabs = QTabWidget()
    window.results_tabs.setDocumentMode(True)

    attention = QWidget()
    attention_layout = QVBoxLayout(attention)
    attention_header = QHBoxLayout()
    window.result_failures_label = QLabel("Nenhuma falha na última execução.")
    window.result_failures_label.setObjectName("subtitle")
    attention_header.addWidget(window.result_failures_label, 1)
    window.retry_failures_button = button("🔁 Repetir falhas", window.retry_failures, primary=True)
    attention_header.addWidget(window.retry_failures_button)
    attention_layout.addLayout(attention_header)
    window.result_failures_table = _table(["Documento", "Fonte", "Erro"], "Documentos com falha")
    window.result_failures_table.setToolTip("Clique duas vezes para abrir o documento na origem")
    window.result_failures_table.cellDoubleClicked.connect(
        lambda row, _column: window._open_failure_origin(row)
    )
    attention_layout.addWidget(window.result_failures_table, 1)
    window.results_tabs.addTab(attention, "⚠ Atenção")

    history = QWidget()
    history_layout = QVBoxLayout(history)
    window.result_history_table = _table(
        ["Data", "Duração", "Novos", "Alterados", "Inalterados", "Falhas"], "Histórico de execuções"
    )
    history_layout.addWidget(window.result_history_table, 1)
    window.results_tabs.addTab(history, "🕘 Histórico")

    report = QWidget()
    report_layout = QVBoxLayout(report)
    report_header = QHBoxLayout()
    report_header.addStretch()
    report_header.addWidget(button("📋 Copiar relatório", window.copy_report))
    report_header.addWidget(button("💾 Exportar", window.export_report))
    report_layout.addLayout(report_header)
    window.result_summary = QTextEdit()
    window.result_summary.setObjectName("logTerminal")
    window.result_summary.setReadOnly(True)
    window.result_summary.setPlaceholderText("✨ Execute uma operação para ver o relatório.")
    report_layout.addWidget(window.result_summary, 1)
    window.results_tabs.addTab(report, "📄 Relatório")

    body.addWidget(window.results_tabs, 1)
    layout.addWidget(window.results_body, 1)
    layout.addStretch(0)  # empty state: leftover space goes below the card, not between header and card
    return page
