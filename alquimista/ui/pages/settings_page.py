from __future__ import annotations

import sys
from typing import Any

from PySide6.QtCore import QRectF, Qt, QTime
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from ..components import SegmentedControl, button, card, page_header, section_title
from ..controllers import schedule_controller
from ..i18n import LANGUAGE_NAMES
from ..theme import DARK, LIGHT

THEMES = [("light", "Claro"), ("dark", "Escuro"), ("system", "Automático")]
UI_SCALES = [(1.0, "100%"), (1.15, "115%"), (1.3, "130%"), (1.5, "150%")]


def _theme_preview(left: dict[str, str], right: dict[str, str]) -> QIcon:
    """Small window drawing (half/half for "Automático") used by the theme tiles."""
    pixmap = QPixmap(176, 104)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for colors, x in ((left, 0), (right, 88)):
        painter.setClipRect(QRectF(x, 0, 88, 104))
        painter.setPen(QColor(colors["border"]))
        painter.setBrush(QColor(colors["window"]))
        painter.drawRoundedRect(QRectF(1, 1, 174, 102), 12, 12)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors["surface"]))
        painter.drawRoundedRect(QRectF(44, 16, 116, 72), 8, 8)
        painter.setBrush(QColor(colors["primary"]))
        painter.drawRoundedRect(QRectF(12, 18, 22, 8), 4, 4)
        painter.setBrush(QColor(colors["muted"]))
        for row in range(3):
            painter.drawRoundedRect(QRectF(56, 28 + row * 16, 80 - row * 18, 6), 3, 3)
    painter.end()
    return QIcon(pixmap)


def _row(title: str, help_text: str, control: QWidget) -> QFrame:
    frame = QFrame()
    frame.setObjectName("optionRow")
    layout = QHBoxLayout(frame)
    layout.setContentsMargins(4, 10, 4, 10)
    text = QVBoxLayout()
    text.setSpacing(0)
    text.addStretch()
    name = QLabel(title)
    name.setObjectName("optionTitle")
    text.addWidget(name)
    if help_text:
        detail = QLabel(help_text)
        detail.setObjectName("subtitle")
        detail.setWordWrap(True)
        text.addWidget(detail)
    text.addStretch()
    layout.addLayout(text, 1)
    if isinstance(control, QPushButton):
        control.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    layout.addWidget(control)
    return frame


def _section(title: str) -> tuple[QScrollArea, QVBoxLayout]:
    """One settings section: a card inside its own scroll area (small windows never squeeze fields)."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    holder = QWidget()
    outer = QVBoxLayout(holder)
    outer.setContentsMargins(0, 0, 8, 0)
    section, layout = card()
    layout.addWidget(section_title(title))
    outer.addWidget(section)
    outer.addStretch()
    scroll.setWidget(holder)
    return scroll, layout


def build_settings_page(window: Any) -> QWidget:
    page, outer = page_header(
        "Configurações",
        "Projeto, aparência, rede e sincronização agendada. Mudanças do projeto ficam pendentes até você salvar.",
        "🔧",
    )
    body = QHBoxLayout()
    body.setSpacing(18)
    window.settings_stack = QStackedWidget()

    project, layout = _section("Projeto")
    window.project_name = QLineEdit()
    window.project_name.setMinimumWidth(280)
    layout.addWidget(_row("Nome do projeto", "A pasta de saída é escolhida na etapa Executar.", window.project_name))
    actions = QHBoxLayout()
    actions.addWidget(button("➕ Novo projeto", window.new_project))
    actions.addWidget(button("📂 Abrir projeto", window.open_project))
    actions.addWidget(button("💾 Salvar como", window.save_project_as, primary=True))
    layout.addLayout(actions)
    window.settings_stack.addWidget(project)

    appearance, layout = _section("Aparência")
    window.theme_combo = QComboBox()
    for value, label in THEMES:
        window.theme_combo.addItem(label, value)
    window.theme_combo.setCurrentIndex(max(0, window.theme_combo.findData(window._theme_preference())))
    window.theme_combo.currentIndexChanged.connect(
        lambda _index: window._set_theme(str(window.theme_combo.currentData()))
    )
    window.theme_combo.setVisible(False)
    layout.addWidget(window.theme_combo)
    previews = {"light": (LIGHT, LIGHT), "dark": (DARK, DARK), "system": (LIGHT, DARK)}
    window.theme_tiles = SegmentedControl(
        [(label, value, _theme_preview(*previews[value])) for value, label in THEMES], tiles=True
    ).bind_combo(window.theme_combo)
    layout.addWidget(_row("Tema", "Automático segue o Windows.", window.theme_tiles))
    window.language_combo = QComboBox()
    for code, label in LANGUAGE_NAMES.items():
        window.language_combo.addItem(label, code)
    window.language_combo.setCurrentIndex(max(0, window.language_combo.findData(window.i18n.language)))
    window.language_combo.currentIndexChanged.connect(
        lambda _index: window._change_language(str(window.language_combo.currentData()))
    )
    layout.addWidget(_row("Idioma da interface", "Textos, botões e mensagens.", window.language_combo))
    window.ui_scale_combo = QComboBox()
    for scale, label in UI_SCALES:
        window.ui_scale_combo.addItem(label, scale)
    window.ui_scale_combo.setCurrentIndex(max(0, window.ui_scale_combo.findData(window._ui_scale_preference())))
    window.ui_scale_combo.currentIndexChanged.connect(
        lambda _index: window._set_ui_scale(float(window.ui_scale_combo.currentData()))
    )
    window.ui_scale_combo.setVisible(False)
    layout.addWidget(window.ui_scale_combo)
    window.ui_scale_pills = SegmentedControl([(label, scale) for scale, label in UI_SCALES]).bind_combo(
        window.ui_scale_combo
    )
    layout.addWidget(_row("Tamanho da interface", "Aumenta textos, botões e ícones. Vale ao reabrir o programa.",
                          window.ui_scale_pills))
    window.settings_stack.addWidget(appearance)

    network, layout = _section("Rede (avançado)")
    help_label = QLabel("Mantenha os valores recomendados se não souber o que alterar.")
    help_label.setObjectName("subtitle")
    layout.addWidget(help_label)
    window.timeout_spin = QSpinBox()
    window.timeout_spin.setRange(5, 600)
    window.retries_spin = QSpinBox()
    window.retries_spin.setRange(1, 10)
    window.delay_spin = QSpinBox()
    window.delay_spin.setRange(0, 60000)
    window.parallel_spin = QSpinBox()
    window.parallel_spin.setRange(1, 16)
    for title, detail, spin in (
        ("Tempo limite de leitura (s)", "Quanto esperar cada resposta do site.", window.timeout_spin),
        ("Tentativas", "Quantas vezes repetir uma página que falhou.", window.retries_spin),
        ("Intervalo entre páginas (ms)", "Pausa para não sobrecarregar o site.", window.delay_spin),
        ("Downloads simultâneos", "Páginas baixadas ao mesmo tempo.", window.parallel_spin),
    ):
        spin.setMinimumWidth(110)
        layout.addWidget(_row(title, detail, spin))
    restore = button("↺ Restaurar valores recomendados", window._restore_network_defaults)
    restore.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
    layout.addWidget(restore, 0, Qt.AlignmentFlag.AlignLeft)
    window.settings_stack.addWidget(network)

    schedule, layout = _section("Sincronização agendada do projeto")
    window.schedule_status = QLabel("")
    window.schedule_status.setObjectName("subtitle")
    window.schedule_status.setWordWrap(True)
    layout.addWidget(window.schedule_status)
    window.schedule_time = QTimeEdit(QTime(2, 0))
    window.schedule_time.setDisplayFormat("HH:mm")
    layout.addWidget(_row("Todos os dias às", "O computador precisa estar ligado nesse horário.", window.schedule_time))
    schedule_actions = QHBoxLayout()
    schedule_actions.addWidget(button("Agendar", lambda: schedule_controller.schedule_daily(window), primary=True))
    schedule_actions.addWidget(button("Remover agendamento", lambda: schedule_controller.remove_schedule(window)))
    layout.addLayout(schedule_actions)
    window.settings_stack.addWidget(schedule)

    help_page, layout = _section("Ajuda")
    layout.addWidget(_row("Tour guiado", "Mostra de novo as 6 etapas do programa.",
                          button("▶ Ver o tour guiado", window.start_tour)))
    layout.addWidget(_row("Projeto de exemplo", "Uma base fictícia para testar sem senha nem token.",
                          button("🧪 Abrir projeto de exemplo", window.open_example_project)))
    window.settings_stack.addWidget(help_page)

    window.settings_menu = SegmentedControl(
        [("Projeto", 0), ("Aparência", 1), ("Rede", 2), ("Agendamento", 3), ("Ajuda", 4)], vertical=True
    ).bind_stack(window.settings_stack)
    window.settings_menu.setFixedWidth(180)
    if sys.platform != "win32":
        window.settings_menu.buttons()[3].setVisible(False)
    body.addWidget(window.settings_menu)
    body.addWidget(window.settings_stack, 1)
    outer.addLayout(body, 1)
    return page
