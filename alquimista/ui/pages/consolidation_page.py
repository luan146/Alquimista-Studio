from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ..components import button, card, page_header


def build_consolidation_page(window: Any) -> QWidget:
    page, layout = page_header(
        "Pacotes para NotebookLM e RAG",
        "Configure as regras de agrupamento e gere pacotes otimizados para envio.",
        "📦",
    )

    splitter = QSplitter(Qt.Orientation.Horizontal)

    controls_scroll = QScrollArea()
    controls_scroll.setWidgetResizable(True)
    controls_scroll.setMinimumWidth(0)
    controls_scroll.setSizePolicy(
        QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
    )
    controls_widget = QWidget()
    controls_layout = QVBoxLayout(controls_widget)
    controls_layout.setContentsMargins(0, 0, 8, 0)
    controls_layout.setSpacing(10)

    controls_card, controls_card_layout = card()
    controls_card.setObjectName("consolidationControlsCard")
    window.con_group = QComboBox()
    for label, value in [
        ("Tudo em uma sequência", "single"),
        ("Separar por fonte", "source"),
        ("Separar por espaço", "space"),
        ("Separar por módulo — profundidade escolhida", "module"),
        ("Separar por módulo e submódulo", "module_submodule"),
        ("Separar por fonte e módulo (recomendado)", "source_module"),
        ("Separar por fonte, módulo e submódulo", "source_module_submodule"),
        ("Grupos definidos manualmente", "manual"),
    ]:
        window.con_group.addItem(label, value)
    window.con_pages = QSpinBox()
    window.con_pages.setRange(1, 10_000)
    window.con_chars = QSpinBox()
    window.con_chars.setRange(1_000, 100_000_000)
    window.con_depth = QSpinBox()
    window.con_depth.setRange(1, 10)
    window.con_depth.setToolTip(
        "1 = primeiro módulo abaixo da raiz; 2 = módulo e submódulo; e assim por diante."
    )
    window.con_depth_choice = QComboBox()
    for level in range(1, 11):
        detail = "módulo principal" if level == 1 else f"módulo + {level - 1} subnível(is)"
        window.con_depth_choice.addItem(f"Nível {level} — {detail}", level)
    window.con_depth_choice.currentIndexChanged.connect(window._depth_choice_changed)
    window.con_depth_example = QLabel()
    window.con_depth_example.setObjectName("subtitle")
    window.con_depth_example.setWordWrap(True)
    window.con_prefix = QLineEdit()
    window.con_hierarchy = QCheckBox("Repetir a árvore no arquivo consolidado")
    window.con_hierarchy.setToolTip(
        "Inclui os níveis do caminho como títulos antes de cada documento."
    )

    def step_frame(number: str, title: str) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("consolidationStep")
        step_layout = QVBoxLayout(frame)
        step_layout.setContentsMargins(14, 12, 14, 12)
        step_layout.setSpacing(8)
        header = QHBoxLayout()
        badge = QLabel(number)
        badge.setObjectName("consolidationStepNumber")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(26, 26)
        header.addWidget(badge)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 11pt; font-weight: 700;")
        header.addWidget(title_label)
        header.addStretch()
        step_layout.addLayout(header)
        return frame, step_layout

    strategy, strategy_layout = step_frame("1", "Estratégia de agrupamento")
    strategy_form = QFormLayout()
    strategy_form.addRow("Agrupamento", window.con_group)
    strategy_layout.addLayout(strategy_form)
    window.con_group_help = QLabel()
    window.con_group_help.setObjectName("subtitle")
    window.con_group_help.setWordWrap(True)
    strategy_layout.addWidget(window.con_group_help)
    controls_card_layout.addWidget(strategy)

    limits, limits_layout = step_frame("2", "Limites do pacote")
    limits_form = QFormLayout()
    limits_form.addRow("Máximo de páginas", window.con_pages)
    limits_form.addRow("Máximo de caracteres", window.con_chars)
    limits_form.addRow("Profundidade dos módulos", window.con_depth_choice)
    limits_layout.addLayout(limits_form)
    limits_layout.addWidget(window.con_depth_example)
    limits_help = QLabel(
        "O pacote respeita os dois limites. Uma página nunca é cortada ao meio; "
        "se exceder sozinha o limite, ela é mantida inteira e sinalizada na prévia."
    )
    limits_help.setObjectName("subtitle")
    limits_help.setWordWrap(True)
    limits_layout.addWidget(limits_help)
    controls_card_layout.addWidget(limits)

    identity, identity_layout = step_frame("3", "Identificação do arquivo")
    identity_form = QFormLayout()
    identity_form.addRow("Prefixo", window.con_prefix)
    identity_form.addRow("Estrutura", window.con_hierarchy)
    identity_layout.addLayout(identity_form)
    window.con_filename_preview = QLabel("Exemplo de arquivo: pacote-01.md")
    window.con_filename_preview.setObjectName("subtitle")
    identity_layout.addWidget(window.con_filename_preview)
    controls_card_layout.addWidget(identity)

    summary = QFrame()
    summary.setObjectName("consolidationSummary")
    summary_layout = QVBoxLayout(summary)
    summary_layout.setContentsMargins(12, 10, 12, 10)
    summary_title = QLabel("ⓘ  Resumo das regras atuais")
    summary_title.setStyleSheet("font-weight: 700;")
    summary_layout.addWidget(summary_title)
    window.con_summary = QLabel()
    window.con_summary.setWordWrap(True)
    summary_layout.addWidget(window.con_summary)
    controls_card_layout.addWidget(summary)

    actions = QHBoxLayout()
    window.preview_consolidation_button = button(
        "👁 Prévia da distribuição", window.preview_consolidation
    )
    window.generate_consolidation_button = button(
        "🚀 Gerar pacotes", window.run_consolidation, primary=True
    )
    actions.addWidget(window.preview_consolidation_button)
    actions.addWidget(window.generate_consolidation_button)
    controls_card_layout.addLayout(actions)
    controls_layout.addWidget(controls_card)
    controls_layout.addStretch()
    controls_scroll.setWidget(controls_widget)
    splitter.addWidget(controls_scroll)

    preview_card, preview_layout = card()
    preview_card.setObjectName("consolidationPreviewCard")
    preview_card.setMinimumWidth(0)
    preview_card.setSizePolicy(
        QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
    )
    preview_header = QHBoxLayout()
    preview_title_block = QVBoxLayout()
    preview_title = QLabel("◉  Prévia da distribuição")
    preview_title.setStyleSheet("font-size: 13pt; font-weight: 700;")
    preview_subtitle = QLabel("Estimativa baseada nas regras atuais.")
    preview_subtitle.setObjectName("subtitle")
    preview_title_block.addWidget(preview_title)
    preview_title_block.addWidget(preview_subtitle)
    preview_header.addLayout(preview_title_block, 1)
    window.con_preview_status = QLabel("◌ Prévia pendente")
    window.con_preview_status.setObjectName("consolidationPreviewStatus")
    preview_header.addWidget(window.con_preview_status, 0, Qt.AlignmentFlag.AlignTop)
    preview_layout.addLayout(preview_header)

    window.con_stat_labels = {}
    stats = QGridLayout()
    stats.setSpacing(8)
    for column, (key, title, suffix) in enumerate(
        [
            ("packages", "Pacotes estimados", "arquivos"),
            ("pages", "Páginas totais", "páginas"),
            ("characters", "Caracteres totais", "caracteres"),
            ("average", "Média por pacote", "páginas"),
        ]
    ):
        metric = QFrame()
        metric.setObjectName("consolidationMetric")
        metric_layout = QVBoxLayout(metric)
        metric_layout.setContentsMargins(10, 10, 10, 8)
        title_label = QLabel(title)
        title_label.setObjectName("subtitle")
        value_label = QLabel("—")
        value_label.setObjectName("consolidationMetricValue")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        suffix_label = QLabel(suffix)
        suffix_label.setObjectName("subtitle")
        suffix_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        metric_layout.addWidget(title_label)
        metric_layout.addWidget(value_label)
        metric_layout.addWidget(suffix_label)
        window.con_stat_labels[key] = value_label
        stats.addWidget(metric, 0, column)
    preview_layout.addLayout(stats)

    window.con_distribution_title = QLabel("Distribuição por grupo")
    window.con_distribution_title.setStyleSheet("font-weight: 700;")
    preview_layout.addWidget(window.con_distribution_title)
    window.con_depth_preview = QLabel()
    window.con_depth_preview.setObjectName("subtitle")
    window.con_depth_preview.setWordWrap(True)
    preview_layout.addWidget(window.con_depth_preview)
    window.package_table = QTableWidget(0, 5)
    window.package_table.setObjectName("consolidationTable")
    window.package_table.setMinimumWidth(0)
    window.package_table.setSizePolicy(
        QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Expanding
    )
    window.package_table.setHorizontalHeaderLabels(
        ["#", "Grupo", "Pacotes", "Páginas", "Caracteres"]
    )
    window.package_table.setAlternatingRowColors(True)
    window.package_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    window.package_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    window.package_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    for column in (2, 3, 4):
        window.package_table.horizontalHeader().setSectionResizeMode(
            column, QHeaderView.ResizeMode.ResizeToContents
        )
    preview_layout.addWidget(window.package_table, 1)
    window.package_table.hide()
    window.con_preview_empty = QLabel(
        "Clique em “Prévia da distribuição” para calcular a estimativa dos pacotes."
    )
    window.con_preview_empty.setObjectName("consolidationEmpty")
    window.con_preview_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.con_preview_empty.setWordWrap(True)
    preview_layout.addWidget(window.con_preview_empty)
    note = QLabel(
        "💡 A prévia é uma estimativa. O resultado final pode variar levemente "
        "de acordo com quebras de página e formatação."
    )
    note.setObjectName("subtitle")
    note.setWordWrap(True)
    preview_layout.addWidget(note)
    splitter.addWidget(preview_card)
    splitter.setSizes([650, 650])
    layout.addWidget(splitter, 1)

    window.con_group.currentIndexChanged.connect(window._update_consolidation_summary)
    window.con_pages.valueChanged.connect(window._update_consolidation_summary)
    window.con_chars.valueChanged.connect(window._update_consolidation_summary)
    window.con_depth.valueChanged.connect(window._update_consolidation_summary)
    window.con_hierarchy.toggled.connect(window._update_consolidation_summary)
    window.con_prefix.textChanged.connect(window._update_consolidation_summary)
    return page

