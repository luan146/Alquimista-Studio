from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ...models import AuthMode
from ..components import VisibleArrowComboBox, animated_button


def build_connection_page(window: Any) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(26, 30, 26, 26)
    layout.setSpacing(12)

    panel = QFrame()
    panel.setObjectName("connectionPanel")
    panel.setMaximumWidth(1120)
    panel.setMinimumWidth(560)
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(52, 38, 52, 38)
    panel_layout.setSpacing(28)

    hero = QHBoxLayout()
    hero.setSpacing(16)
    lock = QLabel("🔐")
    lock.setObjectName("connectionIcon")
    lock.setStyleSheet("font-size: 38pt;")
    hero.addWidget(lock)
    hero_text = QVBoxLayout()
    hero_text.setSpacing(8)
    title = QLabel("Conexão e autenticação")

    title.setObjectName("pageTitle")
    hero_text.addWidget(title)
    subtitle = QLabel(
        "Selecione como o ALQuimista acessará a fonte."
    )
    subtitle.setObjectName("subtitle")
    subtitle.setWordWrap(True)
    subtitle.setAlignment(Qt.AlignmentFlag.AlignLeft)
    subtitle.setMinimumHeight(40)
    hero_text.addWidget(subtitle)
    hero.addLayout(hero_text, 1)
    panel_layout.addLayout(hero)
    separator = QFrame()
    separator.setFrameShape(QFrame.Shape.HLine)
    separator.setObjectName("connectionSeparator")
    panel_layout.addWidget(separator)

    source_row = QHBoxLayout()
    source_label = QLabel("Fonte selecionada")
    source_label.setObjectName("connectionLabel")
    source_row.addWidget(source_label)
    window.connection_source = VisibleArrowComboBox()
    window.connection_source.setObjectName("connectionCombo")
    window.connection_source.setMinimumHeight(50)
    window.connection_source.currentIndexChanged.connect(window._connection_source_changed)
    source_row.addWidget(window.connection_source, 1)
    panel_layout.addLayout(source_row)
    auth_label = QLabel("Modo de autenticação")
    auth_label.setObjectName("connectionLabel")
    panel_layout.addWidget(auth_label)
    window.auth_mode = VisibleArrowComboBox()
    window.auth_mode.setObjectName("connectionCombo")
    window.auth_mode.setMinimumHeight(50)
    for label, mode in [
        ("🔓 Acesso público", AuthMode.PUBLIC),
        ("🌐 Login pelo navegador (recomendado)", AuthMode.BROWSER),
        ("👤 Usuário + token", AuthMode.BASIC),
        ("🔑 Token de acesso pessoal", AuthMode.BEARER),
    ]:
        window.auth_mode.addItem(label, mode.value)
    window.auth_mode.currentIndexChanged.connect(
        lambda: window._auth_mode_changed(str(window.auth_mode.currentData()))
    )
    panel_layout.addWidget(window.auth_mode)

    form = QFormLayout()
    form.setVerticalSpacing(10)
    window.connection_form = form
    window.auth_user = QLineEdit()
    window.auth_user.setPlaceholderText("Usuário ou e-mail")
    window.auth_secret = QLineEdit()
    window.auth_secret.setPlaceholderText("Senha, token ou PAT")
    window.auth_secret.setEchoMode(QLineEdit.EchoMode.Password)
    window.session_status = QLabel("○ Nenhuma sessão salva")
    window.session_status.setObjectName("subtitle")
    form.addRow("Usuário ou e-mail", window.auth_user)
    form.addRow("Senha, token ou PAT", window.auth_secret)
    form.addRow("Sessão do navegador", window.session_status)
    panel_layout.addLayout(form)

    window.connection_state = QLabel("● Modo de acesso não selecionado")
    window.connection_state.setObjectName("connectionState")
    window.connection_state.setAccessibleName("Estado atual da conexão")
    window.connection_state.setWordWrap(True)

    window.login_button = animated_button(
        "🔐 Entrar na fonte",
        window.enter_confluence,
        primary=True,
        accent="#42B8BE",
    )
    window.remove_session_button = animated_button(
        "🗑 Apagar sessão",
        window.remove_session,
        danger=True,
        accent="#F17882",
    )
    connection_actions = QHBoxLayout()
    connection_actions.setContentsMargins(0, 4, 0, 4)
    connection_actions.setSpacing(12)
    # Keep authentication actions together and reserve the destructive action
    # for the saved browser session.
    for action in (
        window.login_button,
        window.remove_session_button,
    ):
        action.setMinimumWidth(0)
        connection_actions.addWidget(action, 1)
    panel_layout.addLayout(connection_actions)

    # Spacer to prevent overlap with connection state label
    panel_layout.addSpacing(12)
    panel_layout.addWidget(window.connection_state, 0, Qt.AlignmentFlag.AlignCenter)

    notice = QLabel(
        "🛡  Segurança: senhas e tokens permanecem somente na memória. "
        "A sessão do navegador só é salva quando você escolhe entrar e pode ser apagada a qualquer momento."
    )
    notice.setObjectName("subtitle")
    notice.setWordWrap(True)
    notice.setAlignment(Qt.AlignmentFlag.AlignCenter)
    panel_layout.addWidget(notice)
    layout.addStretch(1)
    layout.addWidget(panel, 0, Qt.AlignmentFlag.AlignHCenter)
    layout.addStretch(1)
    return page
