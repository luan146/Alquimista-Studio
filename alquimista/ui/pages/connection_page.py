from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSize, Qt
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
from ..components import (
    AlchemistIconAtlas,
    SegmentedControl,
    VisibleArrowComboBox,
    button,
    section_title,
)
from ..icons import svg_icon


def build_connection_panel(window: Any) -> QFrame:
    """Connection of the source selected in the Fontes list (embedded panel)."""
    panel = QFrame()
    panel.setObjectName("connectionPanel")
    panel.setMinimumWidth(320)
    panel_layout = QVBoxLayout(panel)
    panel_layout.setContentsMargins(22, 20, 22, 20)
    panel_layout.setSpacing(14)

    title = QLabel("Conexão")
    title.setObjectName("sectionTitle")
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
    window.auth_mode.setVisible(False)
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
    window.auth_mode_pills = SegmentedControl(
        [
            ("Público", AuthMode.PUBLIC.value, svg_icon("publico", 18)),
            ("Navegador", AuthMode.BROWSER.value, svg_icon("navegador", 18)),
            ("Usuário e token", AuthMode.BASIC.value, svg_icon("usuario", 18)),
            ("Token pessoal", AuthMode.BEARER.value, svg_icon("token", 18)),
        ]
    ).bind_combo(window.auth_mode)
    panel_layout.addWidget(window.auth_mode_pills)

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
    form.addRow("Usuário ou e-mail", window.auth_user)
    form.addRow("Senha, token ou PAT", window.auth_secret)
    form.addRow("", window.remember_secret)
    form.addRow("Sessão do navegador", window.session_status)
    panel_layout.addLayout(form)

    window.connection_state = QLabel("● Modo de acesso não selecionado")
    window.connection_state.setObjectName("connectionState")
    window.connection_state.setAccessibleName("Estado atual da conexão")
    window.connection_state.setWordWrap(True)

    window.login_button = button("🔐 Entrar na fonte", window.enter_confluence)
    window.login_button.setObjectName("googleButton")
    window.login_button.setIconSize(QSize(22, 22))
    window.login_button.setMinimumHeight(48)
    panel_layout.addWidget(window.login_button)

    window.account_card = QFrame()
    window.account_card.setObjectName("accountCard")
    account = QHBoxLayout(window.account_card)
    account.setContentsMargins(12, 10, 12, 10)
    window.account_avatar = QLabel()
    window.account_avatar.setFixedSize(36, 36)
    window.account_avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
    account.addWidget(window.account_avatar)
    who = QVBoxLayout()
    who.setSpacing(0)
    window.account_name = QLabel()
    window.account_name.setObjectName("optionTitle")
    window.account_status = QLabel()
    window.account_status.setObjectName("subtitle")
    who.addWidget(window.account_name)
    who.addWidget(window.account_status)
    account.addLayout(who, 1)
    window.remove_session_button = button("Sair", window.remove_session, danger=True)
    window.remove_session_button.setProperty("ghost", True)
    window.remove_session_button.setToolTip("Apaga a sessão do navegador e o token lembrado deste computador.")
    account.addWidget(window.remove_session_button)
    window.account_card.setVisible(False)
    panel_layout.addWidget(window.account_card)

    panel_layout.addWidget(window.connection_state)

    notice = QLabel(
        "🛡  Segurança: senhas e tokens ficam só na memória, a menos que você marque "
        "“Lembrar neste computador”. A sessão do navegador pode ser apagada a qualquer momento."
    )
    notice.setObjectName("subtitle")
    notice.setWordWrap(True)
    panel_layout.addWidget(notice)

    accounts_title = section_title("Contas conectadas")
    panel_layout.addSpacing(8)
    panel_layout.addWidget(accounts_title)
    accounts_holder = QWidget()
    window.accounts_list_layout = QVBoxLayout(accounts_holder)
    window.accounts_list_layout.setContentsMargins(0, 0, 0, 0)
    window.accounts_list_layout.setSpacing(0)
    panel_layout.addWidget(accounts_holder)
    panel_layout.addStretch(1)
    return panel
