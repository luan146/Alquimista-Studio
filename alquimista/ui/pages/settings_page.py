from __future__ import annotations

import sys
from typing import Any

from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QScrollArea,
    QSpinBox,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ..components import button, card, page_header
from ..controllers import schedule_controller
from ..i18n import LANGUAGE_NAMES

THEMES = [("system", "Automático (sistema)"), ("light", "Claro"), ("dark", "Escuro")]
UI_SCALES = [(1.0, "100%"), (1.15, "115%"), (1.3, "130%"), (1.5, "150%")]


def _card_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-size: 11pt; font-weight: 700;")
    return label


def build_settings_page(window: Any) -> QWidget:
    page, outer = page_header(
        "Configurações",
        "Projeto, aparência, rede e sincronização agendada. Mudanças do projeto ficam pendentes até você salvar.",
        "🔧",
    )
    # Everything below scrolls: on small windows the cards used to be squeezed
    # until their fields disappeared.
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 8, 0)
    layout.setSpacing(12)
    scroll.setWidget(content)
    outer.addWidget(scroll, 1)

    project_card, project_layout = card()
    project_layout.addWidget(_card_title("📁 Projeto"))
    form = QFormLayout()
    window.project_name = QLineEdit()
    form.addRow("Nome do projeto", window.project_name)
    output_help = QLabel("A pasta de saída é escolhida na etapa Executar.")
    output_help.setObjectName("subtitle")
    output_help.setWordWrap(True)
    form.addRow("", output_help)
    project_layout.addLayout(form)
    project_actions = QHBoxLayout()
    project_actions.addWidget(button("➕ Novo projeto", window.new_project))
    project_actions.addWidget(button("📂 Abrir projeto", window.open_project))
    project_actions.addWidget(button("💾 Salvar como", window.save_project_as, primary=True))
    project_layout.addLayout(project_actions)
    layout.addWidget(project_card)

    appearance, appearance_layout = card()
    appearance_layout.addWidget(_card_title("🎨 Aparência"))
    appearance_form = QFormLayout()
    window.theme_combo = QComboBox()
    for value, label in THEMES:
        window.theme_combo.addItem(label, value)
    window.theme_combo.setCurrentIndex(max(0, window.theme_combo.findData(window._theme_preference())))
    window.theme_combo.currentIndexChanged.connect(
        lambda _index: window._set_theme(str(window.theme_combo.currentData()))
    )
    appearance_form.addRow("Tema", window.theme_combo)
    window.language_combo = QComboBox()
    for code, label in LANGUAGE_NAMES.items():
        window.language_combo.addItem(label, code)
    window.language_combo.setCurrentIndex(max(0, window.language_combo.findData(window.i18n.language)))
    window.language_combo.currentIndexChanged.connect(
        lambda _index: window._change_language(str(window.language_combo.currentData()))
    )
    appearance_form.addRow("Idioma da interface", window.language_combo)
    appearance_form.addRow("Perfil visual", window.visual_profile_combo)
    window.ui_scale_combo = QComboBox()
    for scale, label in UI_SCALES:
        window.ui_scale_combo.addItem(label, scale)
    window.ui_scale_combo.setCurrentIndex(max(0, window.ui_scale_combo.findData(window._ui_scale_preference())))
    window.ui_scale_combo.currentIndexChanged.connect(
        lambda _index: window._set_ui_scale(float(window.ui_scale_combo.currentData()))
    )
    window.ui_scale_combo.setToolTip("Aumenta textos, botões e ícones. Vale ao reabrir o programa.")
    appearance_form.addRow("Tamanho da interface", window.ui_scale_combo)
    appearance_layout.addLayout(appearance_form)
    layout.addWidget(appearance)

    network, network_layout = card()
    network_layout.addWidget(_card_title("⚙ Rede (avançado)"))
    network_help = QLabel("Mantenha os valores recomendados se não souber o que alterar.")
    network_help.setObjectName("subtitle")
    network_layout.addWidget(network_help)
    form = QFormLayout()
    window.timeout_spin = QSpinBox()
    window.timeout_spin.setRange(5, 600)
    window.retries_spin = QSpinBox()
    window.retries_spin.setRange(1, 10)
    window.delay_spin = QSpinBox()
    window.delay_spin.setRange(0, 60000)
    window.parallel_spin = QSpinBox()
    window.parallel_spin.setRange(1, 16)
    form.addRow("Timeout de leitura (s)", window.timeout_spin)
    form.addRow("Tentativas", window.retries_spin)
    form.addRow("Intervalo entre páginas (ms)", window.delay_spin)
    form.addRow("Downloads simultâneos", window.parallel_spin)
    network_layout.addLayout(form)
    network_layout.addWidget(button("↺ Restaurar valores recomendados", window._restore_network_defaults))
    layout.addWidget(network)

    schedule, schedule_layout = card()
    schedule_layout.addWidget(_card_title("⏰ Sincronização agendada do projeto"))
    window.schedule_status = QLabel("")
    window.schedule_status.setObjectName("subtitle")
    window.schedule_status.setWordWrap(True)
    schedule_layout.addWidget(window.schedule_status)
    window.schedule_time = QTimeEdit(QTime(2, 0))
    window.schedule_time.setDisplayFormat("HH:mm")
    schedule_row = QHBoxLayout()
    schedule_row.addWidget(QLabel("Todos os dias às"))
    schedule_row.addWidget(window.schedule_time)
    schedule_row.addWidget(button("Agendar", lambda: schedule_controller.schedule_daily(window), primary=True))
    schedule_row.addWidget(button("Remover agendamento", lambda: schedule_controller.remove_schedule(window)))
    schedule_row.addStretch()
    schedule_layout.addLayout(schedule_row)
    schedule.setVisible(sys.platform == "win32")
    layout.addWidget(schedule)

    help_card, help_layout = card()
    help_layout.addWidget(_card_title("❓ Ajuda"))
    help_row = QHBoxLayout()
    help_row.addWidget(button("▶ Ver o tour guiado", window.start_tour))
    help_row.addWidget(button("🧪 Abrir projeto de exemplo", window.open_example_project))
    help_row.addStretch()
    help_layout.addLayout(help_row)
    layout.addWidget(help_card)
    layout.addStretch()
    scroll.setAlignment(Qt.AlignmentFlag.AlignTop)
    return page
