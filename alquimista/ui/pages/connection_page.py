from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from ...models import AuthMode
from ..components import AlchemistIconAtlas, VisibleArrowComboBox, animated_button


def build_connection_panel(window: Any) -> QFrame:
    """Connection of the source selected in the Fontes list (embedded panel)."""
    panel = QFrame()
    panel.setObjectName("connectionPanel")
    panel.setMinimumWidth(320)
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(22, 20, 22, 20)
    panel_layout.setSpacing(14)

    title = QLabel("Conexão")
    title.setStyleSheet("font-size: 13pt; font-weight: 700;")
    panel_layout.addWidget(title)
    window.connection_title = QLabel("Selecione uma fonte na lista.")
    window.connection_title.setObjectName("subtitle")
    window.connection_title.setWordWrap(True)
    panel_layout.addWidget(window.connection_title)

    # The list on the left chooses the source; this combo stays as the internal
    # model the connection handlers read (source_by_combo).
    window.connection_source = VisibleArrowComboBox()
    window.connection_source.setObjectName("connectionCombo")
    window.connection_source.currentIndexChanged.connect(window._connection_source_changed)
    window.connection_source.setVisible(False)
    panel_layout.addWidget(window.connection_source)
    auth_label = QLabel("Modo de autenticação")
    auth_label.setObjectName("connectionLabel")
    panel_layout.addWidget(auth_label)
    window.auth_mode = VisibleArrowComboBox()
    window.auth_mode.setObjectName("connectionCombo")
    window.auth_mode.setMinimumHeight(50)
    for label, mode, icon_index in [
        ("Acesso público", AuthMode.PUBLIC, 0),
        ("Login pelo navegador (recomendado)", AuthMode.BROWSER, 1),
        ("Usuário + token", AuthMode.BASIC, 2),
        ("Token de acesso pessoal", AuthMode.BEARER, 4),
    ]:
        window.auth_mode.addItem(
            AlchemistIconAtlas.auth_icon(icon_index, 24), label, mode.value
        )
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
    window.remember_secret = QCheckBox("Lembrar neste computador")
    window.remember_secret.setToolTip(
        "Guarda o token criptografado para o seu usuário do Windows. Necessário para a sincronização agendada."
    )
    window.session_status = QLabel("○ Nenhuma sessão salva")
    window.session_status.setObjectName("subtitle")
    def auth_field_label(icon_index: int, text: str) -> QWidget:
        label = QWidget()
        label_layout = QHBoxLayout(label)
        label_layout.setContentsMargins(0, 0, 8, 0)
        label_layout.setSpacing(6)
        icon = QLabel()
        icon.setPixmap(AlchemistIconAtlas.auth_pixmap(icon_index, 20))
        label_layout.addWidget(icon)
        label_layout.addWidget(QLabel(text))
        return label

    form.addRow(auth_field_label(2, "Usuário ou e-mail"), window.auth_user)
    form.addRow(auth_field_label(4, "Senha, token ou PAT"), window.auth_secret)
    form.addRow("", window.remember_secret)
    form.addRow(auth_field_label(6, "Sessão do navegador"), window.session_status)
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
    connection_actions = QVBoxLayout()
    connection_actions.setContentsMargins(0, 4, 0, 4)
    connection_actions.setSpacing(12)
    # Keep authentication actions together and reserve the destructive action
    # for the saved browser session.
    for action in (
        window.login_button,
        window.remove_session_button,
    ):
        action.setMinimumWidth(0)
        action.setMinimumHeight(48)
        connection_actions.addWidget(action)
    panel_layout.addLayout(connection_actions)

    # Spacer to prevent overlap with connection state label
    panel_layout.addSpacing(12)
    panel_layout.addWidget(window.connection_state)

    notice = QLabel(
        "🛡  Segurança: senhas e tokens ficam só na memória, a menos que você marque "
        "“Lembrar neste computador”. A sessão do navegador pode ser apagada a qualquer momento."
    )
    notice.setObjectName("subtitle")
    notice.setWordWrap(True)
    panel_layout.addWidget(notice)
    panel_layout.addStretch(1)
    return panel
