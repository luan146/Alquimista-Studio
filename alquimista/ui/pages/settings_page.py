from __future__ import annotations

import sys
from typing import Any

from PySide6.QtCore import QTime
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTimeEdit,
    QWidget,
)

from ..components import button, card, page_header
from ..controllers import schedule_controller
from ..i18n import LANGUAGE_NAMES
from ..theme import apply_theme


def build_settings_page(window: Any) -> QWidget:
    page, layout = page_header(
        "Configurações",
        "Ajuste aparência, rede e comportamento seguro.",
        "🔧",
    )
    settings_help = QLabel(
        "As opções comuns ficam primeiro. Rede é uma área avançada; mantenha os "
        "valores recomendados se não souber o que alterar. Mudanças ficam pendentes "
        "até você salvar o projeto."
    )
    settings_help.setWordWrap(True)
    settings_help.setObjectName("subtitle")
    layout.addWidget(settings_help)
    project_card, project_layout = card()
    form = QFormLayout()
    window.project_name = QLineEdit()
    form.addRow("Nome do projeto", window.project_name)
    output_help = QLabel(
        "A pasta de saída é configurada na etapa 08. As alterações ficam pendentes "
        "até o projeto ser salvo."
    )
    output_help.setObjectName("subtitle")
    output_help.setWordWrap(True)
    form.addRow("", output_help)
    project_layout.addLayout(form)
    project_actions = QHBoxLayout()
    project_actions.addWidget(button("➕ Novo projeto", window.new_project))
    project_actions.addWidget(
        button("📂 Abrir projeto", window.open_project)
    )
    project_actions.addWidget(
        button("💾 Salvar como", window.save_project_as, primary=True)
    )
    project_layout.addLayout(project_actions)
    layout.addWidget(project_card)
    appearance, appearance_layout = card()
    appearance_layout.addWidget(QLabel("🎨 Aparência"))
    window.theme_combo = QComboBox()
    window.theme_combo.addItems(["system", "light", "dark"])
    window.theme_combo.currentTextChanged.connect(
        lambda value: apply_theme(QApplication.instance(), value)
    )
    appearance_layout.addWidget(window.theme_combo)
    language_label = QLabel("🌐 Idioma da interface")
    appearance_layout.addWidget(language_label)
    window.language_combo = QComboBox()
    for code, label in LANGUAGE_NAMES.items():
        window.language_combo.addItem(label, code)
    window.language_combo.setCurrentIndex(
        max(0, window.language_combo.findData(window.i18n.language))
    )
    window.language_combo.currentIndexChanged.connect(
        lambda _index: window._change_language(
            str(window.language_combo.currentData())
        )
    )
    appearance_layout.addWidget(window.language_combo)
    appearance_layout.addWidget(QLabel("Perfil visual"))
    appearance_layout.addWidget(window.visual_profile_combo)
    layout.addWidget(appearance)
    network, network_layout = card()
    network_layout.addWidget(QLabel("⚙ Rede (avançado)"))
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
    network_layout.addWidget(
        button(
            "↺ Restaurar valores recomendados",
            window._restore_network_defaults,
        )
    )
    layout.addWidget(network)

    schedule, schedule_layout = card()
    schedule_layout.addWidget(QLabel("⏰ Sincronização agendada do projeto"))
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
    layout.addStretch()
    return page
