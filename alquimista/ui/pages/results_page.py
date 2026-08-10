from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QHBoxLayout, QLabel, QTextEdit, QWidget

from ..components import button, page_header


def build_results_page(window: Any) -> QWidget:
    page, layout = page_header(
        "Resultados e relatórios",
        "Tudo o que aconteceu, em linguagem clara e com atalhos úteis.",
        "📊",
    )
    result_help = QLabel(
        "✅ Concluído indica sucesso · ⚠ Aviso indica algo que merece revisão · "
        "❌ Erro indica uma página ou arquivo que não pôde ser processado. "
        "Use “Abrir pasta” para acessar todos os arquivos gerados."
    )
    result_help.setWordWrap(True)
    result_help.setObjectName("subtitle")
    layout.addWidget(result_help)
    window.result_summary = QTextEdit()
    window.result_summary.setReadOnly(True)
    window.result_summary.setPlaceholderText("✨ Execute uma operação para ver o relatório.")
    layout.addWidget(window.result_summary, 1)
    actions = QHBoxLayout()
    actions.addWidget(button("📋 Copiar relatório", window.copy_report))
    actions.addWidget(button("📁 Abrir pasta", window.open_output))
    actions.addWidget(button("Copiar caminho", window.copy_output_path))
    actions.addWidget(button("🧾 Abrir manifesto", window.open_manifest))
    actions.addWidget(button("🛠 Abrir log técnico", window.open_log))
    actions.addWidget(button("💾 Exportar relatório", window.export_report))
    actions.addStretch()
    layout.addLayout(actions)
    return page


