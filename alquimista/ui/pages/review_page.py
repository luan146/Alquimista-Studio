from __future__ import annotations

import html
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..components import (
    ResponsiveOutputControls,
    SegmentedControl,
    button,
    card,
    chip,
    page_header,
    section_title,
)
from ..i18n import translate_text
from ..theme import current_colors

_MARKS = {"error": ("✕", "danger"), "warning": ("!", "warning"), "info": ("•", "primary")}


def append_rendered(window: Any, level: str, line: str) -> None:
    """Add one activity line with its colored mark and keep the view at the bottom."""
    mark, color = _MARKS[level]
    first, *rest = line.split("\n")
    window.log_text.append(
        f'<span style="color:{current_colors()[color]}; font-weight:700">{mark}</span> {html.escape(first)}'
    )
    # Multi-line entries (a traceback) keep one row per line and their indentation.
    for extra in rest:
        text = extra.lstrip(" ")
        indent = "&nbsp;" * (2 + len(extra) - len(text))
        window.log_text.append(f"<span>{indent}{html.escape(text)}</span>")  # tag: read as rich text
    bar = window.log_text.verticalScrollBar()
    bar.setValue(bar.maximum())


def render_log(window: Any) -> None:
    """Rebuild the activity list from the stored lines, keeping only the chosen level."""
    wanted = window.log_filter.value() or "all"
    window.log_text.clear()
    for level, line in window._log_entries:
        if wanted in ("all", level):
            append_rendered(window, level, line)


def show_run_monitor(window: Any, visible: bool) -> None:
    window.execute_stack.setCurrentIndex(1 if visible else 0)


def _copy_log(window: Any) -> None:
    QApplication.clipboard().setText("\n".join(line for _level, line in window._log_entries))
    window.notify(translate_text("Registro copiado."), "success")


def build_review_page(window: Any) -> QWidget:
    page, layout = page_header(
        "Executar",
        "Confira se está tudo pronto, escolha a pasta e execute.",
        "🚀",
    )
    window._log_entries = []
    window.execute_stack = QStackedWidget()

    # 1. Preparar
    prepare = QWidget()
    columns = QHBoxLayout(prepare)
    columns.setContentsMargins(0, 0, 0, 0)
    columns.setSpacing(16)
    checklist, checklist_layout = card()
    checklist_layout.addWidget(section_title("Antes de executar"))
    window.review_values = {}
    window.review_status_icons = {}
    # Kept hidden: plain-text summary used by tests and by the copy of the review.
    window.review_summary = QLabel()
    window.review_summary.setVisible(False)
    for label, key, target in [
        ("Fonte", "source", "sources"),
        ("Modo de acesso", "connection", "connection"),
        ("Seleção", "selection", "selection"),
        ("Formato", "format", "markdown"),
        ("Pacotes para IA", "consolidation", "consolidation"),
    ]:
        row = QFrame()
        row.setObjectName("optionRow")
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(4, 8, 4, 8)
        status = QLabel("○")
        status.setObjectName("reviewStatusIcon")
        status.setFixedWidth(18)
        row_layout.addWidget(status)
        text = QVBoxLayout()
        text.setSpacing(0)
        title_label = QLabel(label)
        title_label.setObjectName("optionTitle")
        value = QLabel("Pendente")
        value.setObjectName("subtitle")
        value.setWordWrap(True)
        text.addWidget(title_label)
        text.addWidget(value)
        row_layout.addLayout(text, 1)
        edit = button("Editar", lambda _checked=False, page_key=target: window._show_page(page_key))
        edit.setProperty("ghost", True)
        row_layout.addWidget(edit)
        window.review_values[key] = value
        window.review_status_icons[key] = status
        checklist_layout.addWidget(row)
    checklist_layout.addWidget(window.review_summary)
    checklist_layout.addStretch()
    columns.addWidget(checklist, 1)

    run_side = QVBoxLayout()
    run_side.setSpacing(16)
    operation, operation_layout = card()
    operation_layout.addWidget(section_title("Operação"))
    window.execution_mode = QComboBox()
    window.execution_mode.setAccessibleName("Tipo de operação")
    window.execution_mode.addItem("Extrair e consolidar", "complete")
    window.execution_mode.addItem("Somente extrair páginas", "extract")
    window.execution_mode.addItem("Somente consolidar arquivos já extraídos", "consolidate")
    window.execution_mode.currentIndexChanged.connect(window._update_execution_mode_help)
    window.execution_mode.currentIndexChanged.connect(lambda _index: window._refresh_execute_blocker())
    operation_layout.addWidget(window.execution_mode)
    window.execution_mode_help = QLabel()
    window.execution_mode_help.setObjectName("subtitle")
    window.execution_mode_help.setWordWrap(True)
    operation_layout.addWidget(window.execution_mode_help)
    window.execute_blocker = QLabel()
    window.execute_blocker.setObjectName("reviewInfo")
    window.execute_blocker.setWordWrap(True)
    window.execute_blocker.setTextFormat(Qt.TextFormat.RichText)
    window.execute_blocker.linkActivated.connect(window._show_page)
    window.execute_blocker.setVisible(False)
    operation_layout.addWidget(window.execute_blocker)
    window.execute_button = button("🚀 Executar agora", window.execute_selected_operation, primary=True)
    window.execute_button.setToolTip("Executar (F5)")
    window.execute_button.setMinimumHeight(48)
    operation_layout.addWidget(window.execute_button)
    note = QLabel(
        "Se você cancelar ou fechar o programa, o que já foi extraído fica salvo e a "
        "próxima execução continua do resto."
    )
    note.setObjectName("subtitle")
    note.setWordWrap(True)
    operation_layout.addWidget(note)
    run_side.addWidget(operation)
    output, output_layout = card()
    output_layout.addWidget(section_title("Pasta de saída"))
    window.output_dir = QLineEdit()
    window.output_dir.setAccessibleName("Pasta onde os arquivos serão salvos")
    window.output_dir.setPlaceholderText("Escolha uma pasta no computador")
    window.output_dir.textChanged.connect(window._update_output_preview)
    # Not primary: the only main action on this screen is "Executar agora".
    window.output_controls = ResponsiveOutputControls(
        window.output_dir,
        [button("Escolher pasta", window.choose_output), button("Abrir pasta", window.open_output)],
    )
    output_layout.addWidget(window.output_controls)
    window.output_path_status = QLabel()
    window.output_path_status.setObjectName("subtitle")
    window.output_path_status.setWordWrap(True)
    output_layout.addWidget(window.output_path_status)
    window.output_structure = QLabel()
    window.output_structure.setObjectName("outputStructure")
    window.output_structure.setWordWrap(True)
    output_layout.addWidget(window.output_structure)
    run_side.addWidget(output)

    run_side.addStretch()
    side = QWidget()
    side.setLayout(run_side)
    side_scroll = QScrollArea()
    side_scroll.setWidgetResizable(True)
    side_scroll.setFrameShape(QFrame.Shape.NoFrame)
    side_scroll.setWidget(side)
    columns.addWidget(side_scroll, 1)
    window.execute_stack.addWidget(prepare)

    # 2. Acompanhar
    monitor = QWidget()
    monitor_layout = QVBoxLayout(monitor)
    monitor_layout.setContentsMargins(0, 0, 0, 0)
    monitor_layout.setSpacing(16)
    status_card, status_layout = card()
    headline = QHBoxLayout()
    window.run_count = QLabel("0 de 0")
    window.run_count.setObjectName("runCount")
    headline.addWidget(window.run_count)
    window.progress_label = QLabel("Pronto para executar.")
    window.progress_label.setObjectName("subtitle")
    window.progress_label.setWordWrap(True)
    headline.addWidget(window.progress_label, 1)
    window.cancel_button = button("⏹ Cancelar", window.cancel_operation, danger=True)
    window.cancel_button.setEnabled(False)
    headline.addWidget(window.cancel_button)
    window.run_back_button = button("← Voltar à preparação", lambda: show_run_monitor(window, False))
    window.run_back_button.setEnabled(False)
    headline.addWidget(window.run_back_button)
    status_layout.addLayout(headline)
    window.progress = QProgressBar()
    window.progress.setRange(0, 100)
    window.progress.setTextVisible(False)
    status_layout.addWidget(window.progress)
    chips = QHBoxLayout()
    window.run_done_chip = chip("0 prontas", "success")
    window.run_failed_chip = chip("0 falhas", "neutral")
    window.run_left_chip = chip("0 restantes", "neutral")
    for item in (window.run_done_chip, window.run_failed_chip, window.run_left_chip):
        chips.addWidget(item)
    chips.addStretch()
    status_layout.addLayout(chips)
    monitor_layout.addWidget(status_card)

    activity, activity_layout = card()
    activity_head = QHBoxLayout()
    activity_head.addWidget(section_title("Atividade"))
    activity_head.addStretch()
    window.log_filter = SegmentedControl([("Tudo", "all"), ("Erros", "error"), ("Avisos", "warning")])
    window.log_filter.set_value("all")
    window.log_filter.changed.connect(lambda _value: render_log(window))
    activity_head.addWidget(window.log_filter)
    window.log_copy_button = button("Copiar", lambda: _copy_log(window))
    window.log_copy_button.setProperty("ghost", True)
    window.log_copy_button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    activity_head.addWidget(window.log_copy_button)
    activity_layout.addLayout(activity_head)
    window.log_text = QTextEdit()
    window.log_text.setObjectName("logTerminal")
    window.log_text.setReadOnly(True)
    activity_layout.addWidget(window.log_text, 1)
    monitor_layout.addWidget(activity, 1)
    window.execute_stack.addWidget(monitor)

    layout.addWidget(window.execute_stack, 1)
    window._update_output_preview()
    window._update_execution_mode_help()
    return page
