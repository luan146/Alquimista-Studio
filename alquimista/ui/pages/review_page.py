from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..components import ResponsiveOutputControls, button, page_header


def _section(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("reviewStepCard")
    frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)
    heading = QLabel(title)
    heading.setStyleSheet("font-size: 11pt; font-weight: 700;")
    layout.addWidget(heading)
    return frame, layout


def build_review_page(window: Any) -> QWidget:
    page, layout = page_header(
        "Executar",
        "Confira se está tudo pronto, escolha a pasta e execute.",
        "🚀",
    )
    columns = QHBoxLayout()
    columns.setSpacing(14)

    # 1. Checklist: one line per step, with a shortcut to fix it.
    checklist, checklist_layout = _section("Antes de executar")
    window.review_values = {}
    window.review_status_icons = {}
    # Kept hidden: plain-text summary used by tests and by the copy of the review.
    window.review_summary = QLabel()
    window.review_summary.setVisible(False)
    for icon, label, key, target in [
        ("📄", "Fonte", "source", "sources"),
        ("🔗", "Modo de acesso", "connection", "connection"),
        ("☑", "Seleção", "selection", "selection"),
        ("✍", "Formato", "format", "markdown"),
        ("📦", "Pacotes para IA", "consolidation", "consolidation"),
    ]:
        row = QFrame()
        row.setObjectName("reviewItem")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(10, 8, 10, 8)
        row_layout.setSpacing(10)
        status = QLabel("○")
        status.setObjectName("reviewStatusIcon")
        status.setFixedWidth(18)
        row_layout.addWidget(status)
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 13pt;")
        row_layout.addWidget(icon_label)
        text = QVBoxLayout()
        text.setSpacing(2)
        title_label = QLabel(label)
        title_label.setStyleSheet("font-weight: 700; font-size: 9.5pt;")
        value = QLabel("Pendente")
        value.setObjectName("reviewItemValue")
        value.setWordWrap(True)
        text.addWidget(title_label)
        text.addWidget(value)
        row_layout.addLayout(text, 1)
        row_layout.addWidget(
            button("Editar", lambda _checked=False, page_key=target: window._show_page(page_key))
        )
        window.review_values[key] = value
        window.review_status_icons[key] = status
        checklist_layout.addWidget(row)
    checklist_layout.addWidget(window.review_summary)
    checklist_layout.addStretch()
    columns.addWidget(checklist, 1)

    # 2. Output folder.
    output, output_layout = _section("Pasta de saída")
    output_layout.addWidget(QLabel("Onde deseja salvar os arquivos?"))
    window.output_dir = QLineEdit()
    window.output_dir.setAccessibleName("Pasta onde os arquivos serão salvos")
    window.output_dir.setPlaceholderText("Escolha uma pasta no computador")
    window.output_dir.textChanged.connect(window._update_output_preview)
    window.output_controls = ResponsiveOutputControls(
        window.output_dir,
        [
            button("Escolher pasta", window.choose_output, primary=True),
            button("Abrir pasta", window.open_output),
        ],
    )
    output_layout.addWidget(window.output_controls)
    window.output_path_status = QLabel()
    window.output_path_status.setWordWrap(True)
    output_layout.addWidget(window.output_path_status)
    window.output_structure = QLabel()
    window.output_structure.setObjectName("outputStructure")
    window.output_structure.setWordWrap(True)
    output_layout.addWidget(window.output_structure)
    output_layout.addStretch()
    columns.addWidget(output, 1)

    # 3. Run.
    execution, execution_layout = _section("Execução")
    execution_layout.addWidget(QLabel("Operação"))
    window.execution_mode = QComboBox()
    window.execution_mode.setAccessibleName("Tipo de operação")
    window.execution_mode.addItem("Extrair e consolidar", "complete")
    window.execution_mode.addItem("Somente extrair páginas", "extract")
    window.execution_mode.addItem("Somente consolidar arquivos já extraídos", "consolidate")
    window.execution_mode.currentIndexChanged.connect(window._update_execution_mode_help)
    window.execution_mode.currentIndexChanged.connect(lambda _index: window._refresh_execute_blocker())
    execution_layout.addWidget(window.execution_mode)
    window.execution_mode_help = QLabel()
    window.execution_mode_help.setObjectName("subtitle")
    window.execution_mode_help.setWordWrap(True)
    execution_layout.addWidget(window.execution_mode_help)
    window.execute_blocker = QLabel()
    window.execute_blocker.setObjectName("reviewInfo")
    window.execute_blocker.setWordWrap(True)
    window.execute_blocker.setTextFormat(Qt.TextFormat.RichText)
    window.execute_blocker.linkActivated.connect(window._show_page)
    window.execute_blocker.setVisible(False)
    execution_layout.addWidget(window.execute_blocker)
    window.execute_button = button(
        "🚀 Executar operação escolhida", window.execute_selected_operation, primary=True
    )
    window.execute_button.setToolTip("Executar (F5)")
    window.execute_button.setMinimumHeight(44)
    execution_layout.addWidget(window.execute_button)
    window.progress = QProgressBar()
    window.progress.setRange(0, 100)
    execution_layout.addWidget(window.progress)
    window.progress_label = QLabel("Pronto para executar.")
    window.progress_label.setObjectName("subtitle")
    window.progress_label.setWordWrap(True)
    execution_layout.addWidget(window.progress_label)
    window.cancel_button = button("⏹ Cancelar", window.cancel_operation, danger=True)
    window.cancel_button.setEnabled(False)
    execution_layout.addWidget(window.cancel_button)
    note = QLabel(
        "ⓘ  Se você cancelar ou fechar o programa, o que já foi extraído fica salvo e a "
        "próxima execução continua do resto."
    )
    note.setObjectName("reviewInfo")
    note.setWordWrap(True)
    execution_layout.addWidget(note)
    window.log_text = QTextEdit()
    window.log_text.setObjectName("logTerminal")
    window.log_text.setReadOnly(True)
    window.log_text.setVisible(False)
    execution_layout.addWidget(window.log_text)
    execution_layout.addStretch()
    columns.addWidget(execution, 1)
    layout.addLayout(columns, 1)

    window._update_output_preview()
    window._update_execution_mode_help()
    return page
