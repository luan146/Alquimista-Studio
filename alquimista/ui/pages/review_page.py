from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
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


def build_review_page(window: Any) -> QWidget:
    page, layout = page_header(
        "Revisão final e pasta de saída",
        "Revise suas escolhas, defina a pasta de saída e execute a operação.",
        "🚀",
    )

    step_bar = QHBoxLayout()
    step_bar.setSpacing(12)
    for number, title, detail in [
        ("1", "Revisão das escolhas", "Confira e edite suas configurações"),
        ("2", "Pasta de saída", "Defina onde os arquivos serão salvos"),
        ("3", "Confirmação e execução", "Revise os itens finais e execute a operação"),
    ]:
        badge = QLabel(number)
        badge.setObjectName("consolidationStepNumber")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(36, 36)
        step_bar.addWidget(badge)
        text = QVBoxLayout()
        text.setSpacing(2)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-weight: 700; font-size: 10.5pt;")
        detail_label = QLabel(detail)
        detail_label.setObjectName("subtitle")
        text.addWidget(title_label)
        text.addWidget(detail_label)
        step_bar.addLayout(text, 1)
        if number != "3":
            line = QFrame()
            line.setFrameShape(QFrame.Shape.HLine)
            line.setObjectName("reviewStepLine")
            step_bar.addWidget(line, 1)
    layout.addLayout(step_bar)

    columns = QHBoxLayout()
    columns.setSpacing(14)

    def step_card(number: str, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("reviewStepCard")
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(16, 16, 16, 16)
        frame_layout.setSpacing(12)
        header = QHBoxLayout()
        badge = QLabel(number)
        badge.setObjectName("consolidationStepNumber")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(28, 28)
        header.addWidget(badge)
        heading = QLabel(title)
        heading.setStyleSheet("font-size: 11pt; font-weight: 700;")
        header.addWidget(heading)
        header.addStretch()
        frame_layout.addLayout(header)
        return frame, frame_layout

    choices, choices_layout = step_card("1", "Revisão das escolhas")
    window.review_values = {}
    window.review_summary = QLabel()
    window.review_summary.setVisible(False)

    def review_row(icon: str, label: str, key: str, target: str) -> None:
        row = QFrame()
        row.setObjectName("reviewItem")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(10, 8, 10, 8)
        row_layout.setSpacing(10)
        icon_label = QLabel(icon)
        icon_label.setObjectName("reviewItemIcon")
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
        choices_layout.addWidget(row)

    review_row("📄", "Fonte", "source", "sources")
    review_row("🔗", "Modo de acesso", "connection", "connection")
    review_row("☑", "Seleção", "selection", "selection")
    review_row("✍", "Formato", "format", "markdown")
    review_row("📦", "Consolidação", "consolidation", "consolidation")
    choices_note = QLabel(
        "ⓘ  Deseja modificar alguma escolha? Use os botões ao lado para editar cada etapa."
    )
    choices_note.setObjectName("reviewInfo")
    choices_note.setWordWrap(True)
    choices_layout.addWidget(choices_note)
    choices_layout.addWidget(window.review_summary)
    columns.addWidget(choices, 1)

    output, output_layout = step_card("2", "Pasta de saída")
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
    window.output_subfolder = QCheckBox("Criar uma subpasta para esta execução")
    window.output_subfolder.setChecked(True)
    window.output_subfolder.toggled.connect(window._update_output_preview)
    output_layout.addWidget(window.output_subfolder)
    structure_title = QLabel("Estrutura prevista")
    structure_title.setStyleSheet("font-weight: 700;")
    output_layout.addWidget(structure_title)
    window.output_structure = QLabel()
    window.output_structure.setObjectName("outputStructure")
    window.output_structure.setWordWrap(True)
    output_layout.addWidget(window.output_structure)
    output_note = QLabel(
        "ⓘ  Os arquivos serão organizados conforme a estrutura acima na pasta selecionada."
    )
    output_note.setObjectName("reviewInfo")
    output_note.setWordWrap(True)
    output_layout.addWidget(output_note)
    output_layout.addStretch()
    columns.addWidget(output, 1)

    execution, execution_layout = step_card("3", "Confirmação e execução")
    execution_layout.addWidget(QLabel("Resumo da operação"))
    operation_summary = QFrame()
    operation_summary.setObjectName("reviewOperationSummary")
    operation_summary_layout = QVBoxLayout(operation_summary)
    operation_summary_layout.setContentsMargins(12, 8, 12, 8)
    operation_summary_layout.setSpacing(6)
    for key, title in [
        ("source", "Fonte"),
        ("connection", "Modo de acesso"),
        ("selection", "Seleção"),
        ("format", "Formato"),
        ("consolidation", "Consolidação"),
        ("output", "Pasta de saída"),
    ]:
        row = QHBoxLayout()
        status = QLabel("✓")
        status.setObjectName("reviewStatusIcon")
        row.addWidget(status)
        row.addWidget(QLabel(title), 1)
        value = QLabel("—")
        value.setObjectName("reviewOperationValue")
        value.setWordWrap(True)
        row.addWidget(value, 2)
        operation_summary_layout.addLayout(row)
        window.review_values.setdefault(f"operation_{key}", value)
    execution_layout.addWidget(operation_summary)
    operation_label = QLabel("Operação escolhida")
    operation_label.setStyleSheet("font-weight: 700;")
    execution_layout.addWidget(operation_label)
    window.execution_mode = QComboBox()
    window.execution_mode.setAccessibleName("Tipo de operação")
    window.execution_mode.addItem("Extrair e consolidar", "complete")
    window.execution_mode.addItem("Somente extrair páginas", "extract")
    window.execution_mode.addItem("Somente consolidar arquivos já extraídos", "consolidate")
    window.execution_mode.currentIndexChanged.connect(window._update_execution_mode_help)
    execution_layout.addWidget(window.execution_mode)
    window.execution_mode_help = QLabel()
    window.execution_mode_help.setObjectName("subtitle")
    window.execution_mode_help.setWordWrap(True)
    execution_layout.addWidget(window.execution_mode_help)
    window.progress = QProgressBar()
    window.progress.setRange(0, 100)
    execution_layout.addWidget(window.progress)
    window.progress_label = QLabel("Pronto para executar.")
    window.progress_label.setObjectName("subtitle")
    execution_layout.addWidget(window.progress_label)
    action_row = QHBoxLayout()
    window.cancel_button = button("⏹ Cancelar", window.cancel_operation, danger=True)
    window.cancel_button.setEnabled(False)
    action_row.addWidget(window.cancel_button)
    action_row.addWidget(
        button("🚀 Executar operação escolhida", window.execute_selected_operation, primary=True)
    )
    execution_layout.addLayout(action_row)
    window.log_text = QTextEdit()
    window.log_text.setObjectName("logTerminal")
    window.log_text.setReadOnly(True)
    window.log_text.setVisible(False)
    execution_layout.addWidget(window.log_text)
    columns.addWidget(execution, 1)
    layout.addLayout(columns, 1)

    footer = QHBoxLayout()
    footer_note = QLabel(
        "ⓘ  Ao executar, não será possível desfazer a operação. Certifique-se de que as escolhas estão corretas."
    )
    footer_note.setObjectName("reviewInfo")
    footer_note.setWordWrap(True)
    footer.addWidget(footer_note, 1)
    footer.addWidget(button("← Voltar para Consolidação", lambda: window._show_page("consolidation")))
    layout.addLayout(footer)
    window._update_output_preview()
    window._update_execution_mode_help()
    return page

