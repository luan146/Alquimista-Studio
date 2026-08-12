"""Authentication and connection behavior for MainWindow."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QSignalBlocker, QTimer
from PySide6.QtWidgets import QMessageBox

from ...auth import browser_login, delete_session
from ...client import session_path
from ...models import AuthMode, SourceConfig
from ...runtime import CancellationToken
from ..connector_forms import form_spec
from ..i18n import translate_text


class ConnectionMixin:
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
    connection_source: Any
    connection_form: Any
    login_button: Any
    remove_session_button: Any
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
        basic = mode == AuthMode.BASIC.value
        secret = mode in {AuthMode.BASIC.value, AuthMode.BEARER.value}
        browser = mode == AuthMode.BROWSER.value
        source = self.source_by_combo(self.connection_source) if hasattr(self, "connection_source") else None
        bearer_only = bool(source and form_spec(source.source_type).bearer_only)
        if bearer_only:
            basic = False
            browser = False
            secret = mode == AuthMode.BEARER.value
        self.auth_user.setVisible(basic)
        self.auth_secret.setVisible(secret)
        self.session_status.setVisible(browser)
        for field, visible in [
            (self.auth_user, basic),
            (self.auth_secret, secret),
            (self.session_status, browser),
        ]:
            label = self.connection_form.labelForField(field)
            if label:
                label.setVisible(visible)
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
                public_index = self.auth_mode.findData(AuthMode.BROWSER.value)
                with QSignalBlocker(self.auth_mode):
                    self.auth_mode.setCurrentIndex(public_index)




    def test_connection(self) -> None:
        source = self._store_runtime_secret() or self.source_by_combo(getattr(self, "tree_source", getattr(self, "selection_source", None)))
        if not source:
            QMessageBox.information(
                self, translate_text("Fonte"), translate_text("Adicione uma fonte primeiro.")
            )
            return
        descriptor = self.connector_registry.get(source.source_type)
        if not descriptor.implemented:
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
            QMessageBox.information(
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
            QMessageBox.information(
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
        if not source:
            return
        if (
            QMessageBox.question(
                self,
                translate_text("Apagar sessão"),
                translate_text("Apagar os cookies salvos para esta fonte?"),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        delete_session(source)
        self.secrets.pop(source.id)
        self.connected_sources.discard(source.id)
        self.connection_states[source.id] = translate_text(
            "○ Sessão removida — escolha um modo de acesso"
        )
        self.auth_secret.clear()
        self._connection_source_changed()


    def _connection_source_changed(self) -> None:
        """Load a source without converting public access into browser login."""
        source = self.source_by_combo(self.connection_source)
        if not source:
            return
        descriptor = self.connector_registry.get(source.source_type)
        bearer_only = form_spec(source.source_type).bearer_only
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
        if hasattr(self, "login_button"):
            if source.auth_mode == AuthMode.PUBLIC:
                self.login_button.setText(translate_text("Testar acesso público"))
            elif bearer_only:
                self.login_button.setText(
                    translate_text("Informar token do {name}").format(
                        name=descriptor.display_name
                    )
                )
            else:
                self.login_button.setText(
                    translate_text("Entrar no {name}").format(
                        name=descriptor.display_name
                    )
                )
            self.login_button.setToolTip(
                translate_text("Validar o acesso à fonte usando {name}.").format(
                    name=descriptor.display_name
                )
            )
            self.remove_session_button.setEnabled(session_path(source.id).exists())

    def enter_confluence(self) -> None:
        """Dispatch the action according to the currently selected auth mode."""
        source = self.source_by_combo(self.connection_source)
        if not source:
            QMessageBox.information(
                self, translate_text("Fonte"), translate_text("Adicione uma fonte primeiro.")
            )
            return
        descriptor = self.connector_registry.get(source.source_type)
        if not descriptor.operational:
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
        if form_spec(source.source_type).bearer_only:
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
            QMessageBox.information(
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
        QMessageBox.information(
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
                }
            )
            updated = SourceConfig.model_validate(updated.model_dump())
            index = self.project.sources.index(source)
            self.project.sources[index] = updated
            self.secrets.set(updated.id, self.auth_secret.text())
            return updated
        except Exception as exc:
            QMessageBox.warning(
                self, translate_text("Configuração de acesso inválida"), str(exc)
            )
            return None
