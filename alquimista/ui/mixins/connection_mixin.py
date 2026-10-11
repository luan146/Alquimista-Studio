"""Authentication and connection behavior for MainWindow."""

from __future__ import annotations

import re
from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from ...auth import browser_login, delete_session
from ...models import AuthMode, SourceConfig
from ...runtime import CancellationToken
from ...session_store import delete_secret, save_secret, session_exists, session_path
from ..components import inform
from ..i18n import translate_text
from ..icons import svg_icon
from . import WindowBase


def initials(text: str) -> str:
    """'luan@empresa.com' -> 'LU', 'Wiki de Suporte' -> 'WS' (short words are skipped)."""
    words = [word for word in re.split(r"[^\w]+", text.split("@")[0]) if word]
    long_words = [word for word in words if len(word) > 2] or words
    if not long_words:
        return "?"
    if len(long_words) == 1:
        return long_words[0][:2].upper()
    return (long_words[0][0] + long_words[1][0]).upper()


class ConnectionMixin(WindowBase):
    """Connection and authentication behavior."""

    # Attributes provided by MainWindow.__init__/build_connection_page. See
    # TreeMixin for the same pattern: annotations only, no initializers.
    project: Any
    secrets: Any
    connector_registry: Any
    view_state: Any
    connection_states: Any
    connection_state: Any
    connected_sources: Any
    auth_mode: Any
    auth_user: Any
    auth_secret: Any
    remember_secret: Any
    connection_source: Any
    connection_form: Any
    login_button: Any
    remove_session_button: Any
    auth_mode_pills: Any
    account_card: Any
    account_avatar: Any
    account_name: Any
    account_status: Any
    accounts_list_layout: Any
    _source_connection_badge: Any
    _refresh_workflow_state: Any
    session_status: Any
    src_root_mode: Any
    current_source: Any
    source_by_combo: Any
    mark_dirty: Any
    _start_worker: Any
    _lookup_page_details: Any
    _show_page: Any
    load_tree: Any





    def _auth_mode_changed(self, mode: str) -> None:
        source = self.source_by_combo(self.connection_source) if hasattr(self, "connection_source") else None
        self._show_auth_fields(mode, source)
        if source:
            try:
                updated = source.model_copy(
                    update={
                        "auth_mode": AuthMode(mode),
                        "username": self.auth_user.text().strip(),
                    }
                )
                updated = SourceConfig.model_validate(updated.model_dump())
                self.project.sources[self.project.sources.index(source)] = updated
                self.mark_dirty()
            except Exception as exc:
                QMessageBox.warning(
                    self, translate_text("Configuração de acesso inválida"), str(exc)
                )
                # Go back to the last valid mode saved on the source.
                with QSignalBlocker(self.auth_mode):
                    self.auth_mode.setCurrentIndex(self.auth_mode.findData(source.auth_mode.value))
                self._show_auth_fields(source.auth_mode.value, source)
        self._refresh_accounts()

    def _show_auth_fields(self, mode: str, source: SourceConfig | None) -> None:
        basic = mode == AuthMode.BASIC.value
        secret = mode in {AuthMode.BASIC.value, AuthMode.BEARER.value}
        browser = mode == AuthMode.BROWSER.value
        descriptor = self.connector_registry.get(source.source_type) if source else None
        if descriptor and descriptor.form.bearer_only:
            basic = False
            browser = False
            secret = mode == AuthMode.BEARER.value
        for field, visible in [
            (self.auth_user, basic),
            (self.auth_secret, secret),
            (self.remember_secret, secret),
            (self.session_status, browser),
        ]:
            field.setVisible(visible)
            label = self.connection_form.labelForField(field)
            if label:
                label.setVisible(visible)
        if hasattr(self, "auth_mode_pills"):
            # Callers change auth_mode under QSignalBlocker, which bypasses the pills' binding.
            self.auth_mode_pills.set_value(self.auth_mode.currentData())
        if source is not None and descriptor is not None:
            self._refresh_login_button(mode, descriptor)

    def _refresh_login_button(self, mode: str, descriptor: Any) -> None:
        """Text and icon of the sign-in button for the mode chosen in the pills."""
        if not hasattr(self, "login_button"):
            return
        bearer_only = descriptor.form.bearer_only
        if bearer_only:
            mode = AuthMode.BEARER.value
        if mode == AuthMode.PUBLIC.value:
            text = translate_text("Testar acesso público")
        elif bearer_only:
            text = translate_text("Informar token do {name}").format(name=descriptor.display_name)
        else:
            text = translate_text("Entrar no {name}").format(name=descriptor.display_name)
        self.login_button.setText(text)
        self.login_button.setToolTip(
            translate_text("Validar o acesso à fonte usando {name}.").format(name=descriptor.display_name)
        )
        icon_name = {
            AuthMode.PUBLIC.value: "publico", AuthMode.BROWSER.value: "navegador",
            AuthMode.BASIC.value: "usuario", AuthMode.BEARER.value: "token",
        }.get(mode, "chave")
        self.login_button.setIcon(svg_icon(icon_name, 22))




    def test_connection(self) -> None:
        source = self._store_runtime_secret() or self.source_by_combo(getattr(self, "tree_source", getattr(self, "selection_source", None)))
        if not source:
            inform(
                self, translate_text("Fonte"), translate_text("Adicione uma fonte primeiro.")
            )
            return
        descriptor = self.connector_registry.get(source.source_type)
        if not descriptor.runnable:
            self.connection_states[source.id] = translate_text(
                "{name}: em desenvolvimento"
            ).format(name=descriptor.display_name)
            self.connection_state.setText(self.connection_states[source.id])
            return
        self.connection_states[source.id] = translate_text(
            "Conectando via {name}…"
        ).format(name=descriptor.integration_name)
        self.connection_state.setText(self.connection_states[source.id])

        def work(token: CancellationToken, progress: Any, log: Any) -> dict[str, Any]:
            progress(0, 1, translate_text("Conectando…"))
            with self.connector_registry.create(
                source,
                options=self.project.extraction,
                secret=self.secrets.get(source.id, ""),
                token=token,
                log=log,
            ) as connector:
                result = connector.validate_connection()
            progress(1, 1, translate_text("Conexão concluída"))
            return result

        def done(result: dict[str, Any]) -> None:
            self.connected_sources.add(source.id)
            if source.auth_mode == AuthMode.PUBLIC:
                state = (
                    translate_text(
                        "Conexão pública válida — somente páginas públicas serão consideradas"
                    )
                )
                success_message = (
                    translate_text(
                        "Conexão pública válida. Sem login, somente páginas públicas poderão "
                        "ser localizadas e extraídas."
                    )
                )
            else:
                identity = source.username or "conta autenticada"
                state = translate_text(
                    "Conexão autenticada válida — conectado como: {identity}"
                ).format(identity=identity)
                success_message = (
                    translate_text(
                        "Login realizado. A extração poderá acessar as páginas disponíveis "
                        "para esta conta."
                    )
                )
            self.connection_states[source.id] = state
            self.connection_state.setText(state)
            inform(
                self,
                translate_text("Conexão concluída"),
                translate_text(
                    "✅ {message}\nEspaços disponíveis para sua conta: {spaces}"
                ).format(message=success_message, spaces=result["spaces_visible"]),
            )
            if self.current_source() is source and self.src_root_mode.currentData() == "id":
                QTimer.singleShot(100, self._lookup_page_details)
            self._show_page("selection")
            self.load_tree()

        self._start_worker(work, done)


    def start_browser_login(self) -> None:
        source = self._store_runtime_secret()
        if not source:
            return
        self.connection_states[source.id] = translate_text(
            "Aguardando autenticação no navegador…"
        )
        self.connection_state.setText(self.connection_states[source.id])

        def work(token: CancellationToken, progress: Any, log: Any) -> bool:
            progress(0, 1, translate_text("Aguardando login no navegador"))
            browser_login(source, token=token)
            progress(1, 1, translate_text("Sessão salva"))
            return True

        def done(_result: bool) -> None:
            self.connection_states[source.id] = (
                translate_text("Login concluído — carregando os espaços disponíveis…")
            )
            self._connection_source_changed()
            inform(
                self,
                translate_text("Login"),
                translate_text(
                    "✅ Login realizado. A sessão foi salva com seu consentimento. "
                    "O acesso será limitado às permissões desta conta."
                ),
            )
            self._show_page("selection")
            self.load_tree()
        self._start_worker(work, done)


    def remove_session(self) -> None:
        source = self.source_by_combo(self.connection_source)
        if source:
            self._sign_out(source.id)

    def _sign_out(self, source_id: str) -> None:
        source = next((item for item in self.project.sources if item.id == source_id), None)
        if source is None:
            return
        if (
            QMessageBox.question(
                self,
                translate_text("Sair da conta"),
                translate_text(
                    "Sair de {name}? A sessão do navegador e o token lembrado serão apagados deste computador."
                ).format(name=source.name),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        # The remembered token goes first: a failure deleting the browser session/cache must not keep it.
        delete_secret(source.id)
        self.secrets.pop(source.id)
        cleanup_error: Exception | None = None
        try:
            delete_session(source)
        except Exception as exc:  # the token is already gone: finish signing out, then warn
            cleanup_error = exc
        self.connected_sources.discard(source.id)
        self.connection_states[source.id] = translate_text("○ Você saiu — escolha um modo de acesso")
        current = self.source_by_combo(self.connection_source)
        if current is not None and current.id == source.id:
            self.auth_secret.clear()
            self._connection_source_changed()
        self._refresh_workflow_state()
        if cleanup_error is not None:
            QMessageBox.warning(
                self,
                translate_text("Sair da conta"),
                translate_text(
                    "O token foi apagado, mas a sessão do navegador não pôde ser removida por completo: {error}"
                ).format(error=cleanup_error),
            )

    def _account_identity(self, source: SourceConfig) -> tuple[str, str]:
        if source.source_type == "local_files":
            return "📁", translate_text("Pasta local")
        if source.auth_mode == AuthMode.PUBLIC:
            return "🌐", translate_text("Acesso público")
        if source.username:
            return initials(source.username), source.username
        if source.auth_mode == AuthMode.BROWSER:
            return initials(source.name), translate_text("Sessão do navegador")
        return initials(source.name), translate_text("Token salvo")

    def _has_saved_login(self, source: SourceConfig) -> bool:
        # File existence only: this runs on every workflow refresh, so no DPAPI decrypt here.
        return (
            source.id in self.connected_sources
            or bool(self.secrets.get(source.id, ""))
            or session_exists(source.id)
            or session_path(source.id, "secret").exists()
        )

    def _avatar_style(self, label: QLabel, text: str) -> None:
        from ..space_cards import tile_colors

        background, foreground = tile_colors(text)
        label.setText(text)
        label.setStyleSheet(
            f"background: {background}; color: {foreground}; border-radius: 18px; font-weight: 700;"
        )

    def _refresh_accounts(self) -> None:
        if not hasattr(self, "account_card"):
            return
        source = self.source_by_combo(self.connection_source)
        connected = (
            source is not None
            and source.id in self.connected_sources
            and source.auth_mode != AuthMode.PUBLIC
            and source.source_type != "local_files"
        )
        self.account_card.setVisible(connected)
        self.login_button.setVisible(not connected)
        if source is not None and connected:
            badge, name = self._account_identity(source)
            self._avatar_style(self.account_avatar, badge)
            self.account_name.setText(name)
            self.account_status.setText(translate_text("● Conectado agora"))
        layout = self.accounts_list_layout
        while layout.count():
            widget = layout.takeAt(0).widget()
            if widget is not None:
                widget.hide()  # deleteLater only runs back in the event loop; don't paint stale rows
                widget.deleteLater()
        for each in self.project.sources:
            row = QFrame()
            row.setObjectName("optionRow")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(2, 6, 2, 6)
            avatar = QLabel()
            avatar.setFixedSize(36, 36)
            avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge, name = self._account_identity(each)
            self._avatar_style(avatar, badge)
            row_layout.addWidget(avatar)
            text = QVBoxLayout()
            text.setSpacing(0)
            title = QLabel(name)
            title.setObjectName("optionTitle")
            detail = QLabel(f"{each.name} · {self._source_connection_badge(each)}")
            detail.setObjectName("subtitle")
            text.addWidget(title)
            text.addWidget(detail)
            row_layout.addLayout(text, 1)
            if each.auth_mode != AuthMode.PUBLIC and each.source_type != "local_files" and self._has_saved_login(each):
                leave = QPushButton(translate_text("Sair"))
                leave.setProperty("ghost", True)
                leave.setProperty("danger", True)
                leave.clicked.connect(lambda _checked=False, sid=each.id: self._sign_out(sid))
                row_layout.addWidget(leave)
            layout.addWidget(row)

    def _connection_source_changed(self) -> None:
        """Load a source without converting public access into browser login."""
        source = self.source_by_combo(self.connection_source)
        if not source:
            return
        descriptor = self.connector_registry.get(source.source_type)
        if hasattr(self, "connection_title"):
            self.connection_title.setText(
                translate_text("Fonte: {name} ({platform})").format(
                    name=source.name, platform=descriptor.display_name
                )
            )
        bearer_only = descriptor.form.bearer_only
        for index in range(self.auth_mode.count()):
            item = self.auth_mode.model().item(index)
            if item is not None:
                item.setEnabled(
                    not bearer_only
                    or self.auth_mode.itemData(index) == AuthMode.BEARER.value
                )
        if bearer_only and source.auth_mode != AuthMode.BEARER:
            source.auth_mode = AuthMode.BEARER
        mode_index = self.auth_mode.findData(source.auth_mode.value)
        with QSignalBlocker(self.auth_mode):
            self.auth_mode.setCurrentIndex(mode_index if mode_index >= 0 else -1)
        self.auth_user.setText(source.username)
        self.auth_secret.setText(self.secrets.get(source.id, ""))
        self.remember_secret.setChecked(source.remember_secret)
        self.session_status.setText(
            translate_text("Sessão disponível")
            if session_path(source.id).exists()
            else translate_text("Nenhuma sessão salva")
        )
        self._auth_mode_changed(source.auth_mode.value)
        if source.id in self.connection_states:
            self.connection_state.setText(self.connection_states[source.id])
        elif source.auth_mode == AuthMode.PUBLIC:
            self.connection_state.setText(
                translate_text("Acesso público selecionado — ainda não testado")
            )
        elif session_path(source.id).exists():
            self.connection_state.setText(
                translate_text(
                    "Sessão disponível para {source} — teste a conexão"
                ).format(source=source.username or translate_text("esta fonte"))
            )
        else:
            self.connection_state.setText(
                translate_text("Modo autenticado selecionado — não conectado")
            )
        # Login button text/icon and the account card were refreshed by _auth_mode_changed above.
        if hasattr(self, "auth_mode_pills"):
            self.auth_mode_pills.sync_enabled_from(self.auth_mode)

    def enter_confluence(self) -> None:
        """Dispatch the action according to the currently selected auth mode."""
        source = self.source_by_combo(self.connection_source)
        if not source:
            inform(
                self, translate_text("Fonte"), translate_text("Adicione uma fonte primeiro.")
            )
            return
        descriptor = self.connector_registry.get(source.source_type)
        if not descriptor.runnable:
            self.connection_states[source.id] = (
                translate_text(
                    "{name}: o conector ainda está em desenvolvimento"
                ).format(name=descriptor.display_name)
            )
            self.connection_state.setText(self.connection_states[source.id])
            return
        raw_mode = self.auth_mode.currentData()
        try:
            mode = AuthMode(str(raw_mode)) if raw_mode else source.auth_mode
        except ValueError:
            mode = source.auth_mode
        if descriptor.form.bearer_only:
            mode = AuthMode.BEARER
            with QSignalBlocker(self.auth_mode):
                self.auth_mode.setCurrentIndex(self.auth_mode.findData(mode.value))
        if mode == AuthMode.PUBLIC:
            self.test_connection()
            return
        if mode == AuthMode.BROWSER:
            self.connection_states[source.id] = translate_text(
                "Login iniciado — aguardando autenticação"
            )
            self.connection_state.setText(self.connection_states[source.id])
            self.mark_dirty()
            self.start_browser_login()
            return
        if mode == AuthMode.BASIC:
            if not self.auth_user.text().strip():
                self.auth_user.setFocus()
                self.connection_states[source.id] = translate_text(
                    "Informe o usuário antes de entrar"
                )
                self.connection_state.setText(self.connection_states[source.id])
                return
        if mode in {AuthMode.BASIC, AuthMode.BEARER}:
            if not self.auth_secret.text().strip():
                self.auth_secret.setFocus()
                self.connection_states[source.id] = translate_text(
                    "Informe o token antes de entrar"
                )
                self.connection_state.setText(self.connection_states[source.id])
                return
            self.test_connection()
            return
        self.connection_state.setText(
            translate_text("Selecione um método de autenticação válido")
        )

    def continue_without_login(self) -> None:
        """Select public access for the current source without starting a login."""
        source = self.source_by_combo(self.connection_source)
        if not source:
            inform(
                self, translate_text("Fonte"), translate_text("Adicione uma fonte primeiro.")
            )
            return
        public_index = self.auth_mode.findData(AuthMode.PUBLIC.value)
        with QSignalBlocker(self.auth_mode):
            self.auth_mode.setCurrentIndex(public_index)
        self._auth_mode_changed(AuthMode.PUBLIC.value)
        updated = self.source_by_combo(self.connection_source) or source
        state = translate_text("Sem login — somente páginas públicas serão consideradas")
        self.connection_states[updated.id] = state
        self.connection_state.setText(state)
        inform(
            self,
            translate_text("Acesso público"),
            translate_text(
                "A conexão continuará sem login; somente páginas públicas serão consideradas."
            ),
        )
        self.mark_dirty()

    def _store_runtime_secret(self) -> SourceConfig | None:
        source = self.source_by_combo(self.connection_source)
        if not source:
            return None
        try:
            raw_mode = self.auth_mode.currentData()
            auth_mode = AuthMode(str(raw_mode)) if raw_mode else source.auth_mode
            updated = source.model_copy(
                update={
                    "auth_mode": auth_mode,
                    "username": self.auth_user.text().strip(),
                    "remember_secret": self.remember_secret.isChecked(),
                }
            )
            updated = SourceConfig.model_validate(updated.model_dump())
            index = self.project.sources.index(source)
            self.project.sources[index] = updated
            self.secrets.set(updated.id, self.auth_secret.text())
            if updated.remember_secret and self.auth_secret.text():
                save_secret(updated.id, self.auth_secret.text())
            else:
                delete_secret(updated.id)
            return updated
        except Exception as exc:
            QMessageBox.warning(
                self, translate_text("Configuração de acesso inválida"), str(exc)
            )
            return None
