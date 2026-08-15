import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
)

from ...auth import delete_session
from ...client import ConfluenceClient
from ...confluence_url import parse_confluence_url
from ...models import AuthMode, SourceConfig, now_iso
from ...runtime import CancellationToken
from ...source_detection import DetectedSource, detect_source_url
from ..i18n import translate_text
from ..source_controller import source_by_combo as resolve_source_by_combo
from ..source_controller import source_by_index as resolve_source_by_index
from ..workers import Worker


class SourceMixin:
    """Source list, source form, and source profile behavior."""

    # Attributes provided by MainWindow.__init__/build_*_page. Declared as
    # class annotations (without initializers) so mypy can resolve them while
    # the runtime values are still assigned by MainWindow. Types are kept loose
    # (Any) for widgets/helpers created externally, matching the pattern in
    # TreeMixin.
    project: Any
    view_state: Any
    connector_registry: Any
    secrets: Any
    sources_list: Any
    source_table: Any
    connection_source: Any
    source_name_input: Any
    source_url_input: Any
    src_platform: Any
    src_name: Any
    src_url: Any
    src_url_label: Any
    src_enabled: Any
    src_space: Any
    src_space_label: Any
    src_space_name: Any
    src_space_name_label: Any
    src_include_root: Any
    src_root: Any
    src_root_mode: Any
    src_autofill_status: Any
    source_add_button: Any
    source_cancel_button: Any
    source_count_label: Any
    source_detection_status: Any
    sources_empty_label: Any
    trees: Any
    selection_store: Any
    connection_states: Any
    mark_dirty: Any
    thread_pool: Any
    statusBar: Any
    worker: Any
    page_lookup_worker: "Worker | None"
    _editing_source_row: int | None
    _source_added_at: dict[str, str]
    _active_page_container: str | None
    _active_selection_container: str | None
    _page_render_limits: dict[tuple[str, str], int]
    _selection_render_limits: dict[tuple[str, str], int]
    _connection_source_changed: Any
    _selection_source_changed: Any
    _tree_source_changed: Any

    @property
    def connected_sources(self) -> set[str]:
        return self.view_state.connected_sources


    def _refresh_source_widgets(self) -> None:
        current_source = self.current_source()
        current_id = current_source.id if current_source else None
        blockers = [
            QSignalBlocker(self.sources_list),
            QSignalBlocker(self.connection_source),
        ]
        if hasattr(self, "tree_source"):
            blockers.append(QSignalBlocker(self.tree_source))
        if hasattr(self, "selection_source"):
            blockers.append(QSignalBlocker(self.selection_source))
        self.sources_list.clear()
        self.connection_source.clear()
        if hasattr(self, "tree_source"):
            self.tree_source.clear()
        if hasattr(self, "selection_source"):
            self.selection_source.clear()
        for source in self.project.sources:
            try:
                descriptor = self.connector_registry.get(source.source_type)
                type_label = descriptor.display_name
            except ValueError:
                type_label = source.source_type
            label = f'{source.name} ({type_label})'
            self.sources_list.addItem(source.name)
            self.connection_source.addItem(label, source.id)
            if hasattr(self, "tree_source"):
                self.tree_source.addItem(label, source.id)
            if hasattr(self, "selection_source"):
                self.selection_source.addItem(label, source.id)
        index = next(
            (i for i, source in enumerate(self.project.sources) if source.id == current_id),
            0,
        )
        if self.project.sources:
            self.sources_list.setCurrentRow(index)
            self.connection_source.setCurrentIndex(index)
            if hasattr(self, "tree_source"):
                self.tree_source.setCurrentIndex(index)
            if hasattr(self, "selection_source"):
                self.selection_source.setCurrentIndex(index)
        connection_source = self.source_by_combo(self.connection_source)
        try:
            if connection_source is not None:
                self.connector_registry.get(connection_source.source_type)
        except ValueError:
            assert connection_source is not None
            if hasattr(self, "connection_state"):
                self.connection_state.setText(
                    translate_text(
                        "Conector não registrado ({source_type}) — conexão bloqueada"
                    ).format(source_type=connection_source.source_type)
                )
            if hasattr(self, "auth_secret"):
                self.auth_secret.clear()
            if hasattr(self, "login_button"):
                self.login_button.setEnabled(False)
        else:
            if hasattr(self, "login_button"):
                self.login_button.setEnabled(True)
            self._connection_source_changed()
        if hasattr(self, "tree_source"):
            self._tree_source_changed()
        if hasattr(self, "selection_source"):
            self._selection_source_changed()
        # The source-list signal is blocked while indexes are restored.
        # Explicitly reload the form so the active source, authentication
        # settings, and enabled flag cannot remain from the previous row.
        if self.project.sources:
            self._source_selected(index)
        self._refresh_source_table()


    def _refresh_source_table(self) -> None:
        visible_rows = [
            index
            for index, source in enumerate(self.project.sources)
            if source.base_url or source.connector_options.get("source_url")
        ]
        self._visible_source_rows = visible_rows
        self.source_table.setRowCount(len(visible_rows))
        for table_row, project_row in enumerate(visible_rows):
            source = self.project.sources[project_row]
            checkbox = QTableWidgetItem()
            checkbox.setFlags(
                checkbox.flags() | Qt.ItemFlag.ItemIsUserCheckable
            )
            checkbox.setCheckState(Qt.CheckState.Unchecked)
            checkbox.setData(Qt.ItemDataRole.UserRole, project_row)
            self.source_table.setItem(table_row, 0, checkbox)

            original_url = str(source.connector_options.get("source_url") or source.base_url)
            self.source_table.setItem(table_row, 1, QTableWidgetItem(original_url))
            self.source_table.setItem(table_row, 2, QTableWidgetItem(source.name))
            try:
                descriptor = self.connector_registry.get(source.source_type)
                api_label = f"{descriptor.display_name} · {descriptor.integration_name}"
            except ValueError:
                api_label = translate_text(
                    "{source_type} · Conector não registrado"
                ).format(source_type=source.source_type)
            self.source_table.setItem(table_row, 3, QTableWidgetItem(api_label))
            added_at = self._source_added_at.get(source.id, now_iso())
            self._source_added_at.setdefault(source.id, added_at)
            self.source_table.setItem(table_row, 4, QTableWidgetItem(added_at))

            menu = QPushButton("⋮")
            menu.setToolTip(translate_text("Opções da fonte (sincronizar, editar, remover)"))
            menu.setAccessibleName(
                translate_text("Opções da fonte {name}").format(name=source.name)
            )

            def make_menu_handler(src_id: str, row_idx: int, btn: QPushButton) -> Any:
                def show_menu() -> None:
                    pop = QMenu(self)
                    act_sync = pop.addAction("🔄 " + translate_text("Sincronizar fonte"))
                    act_edit = pop.addAction("✏️ " + translate_text("Editar configurações"))
                    pop.addSeparator()
                    act_rem = pop.addAction("🗑 " + translate_text("Remover fonte"))
                    selected = pop.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
                    if selected == act_sync:
                        self.sync_source(src_id)
                    elif selected == act_edit:
                        self._edit_source_row(row_idx)
                    elif selected == act_rem:
                        self.source_table.selectRow(row_idx)
                        self.remove_selected_sources()
                return show_menu

            menu.clicked.connect(make_menu_handler(source.id, table_row, menu))
            self.source_table.setCellWidget(table_row, 5, menu)
            self.source_table.setRowHeight(table_row, 44)

        self.source_count_label.setText(
            translate_text("{count} itens").format(count=len(visible_rows))
        )
        self.sources_empty_label.setVisible(not visible_rows)

    def sync_source(self, source_id: str) -> None:
        from ..controllers.execution_controller import sync_source as ctrl_sync_source
        ctrl_sync_source(self, source_id)

    def sync_project(self) -> None:
        from ..controllers.execution_controller import sync_project as ctrl_sync_project
        ctrl_sync_project(self)


    def _source_table_row_changed(self, row: int) -> None:
        if row < 0 or row >= len(getattr(self, "_visible_source_rows", [])):
            return
        project_row = self._visible_source_rows[row]
        if self.sources_list.currentRow() != project_row:
            self.sources_list.setCurrentRow(project_row)


    def _selected_source_rows(self) -> list[int]:
        selected: list[int] = []
        for table_row in range(self.source_table.rowCount()):
            item = self.source_table.item(table_row, 0)
            if item and item.checkState() == Qt.CheckState.Checked:
                selected.append(int(item.data(Qt.ItemDataRole.UserRole)))
        if selected:
            return selected
        current_row = self.source_table.currentRow()
        if 0 <= current_row < len(self._visible_source_rows):
            return [self._visible_source_rows[current_row]]
        return []


    def _preview_detected_source(self) -> None:
        raw = self.source_url_input.text().strip()
        if not raw:
            self.source_detection_status.setText(
                translate_text(
                    "A plataforma, a API e os detalhes iniciais serão identificados pela URL."
                )
            )
            return
        try:
            detected = detect_source_url(raw, self.connector_registry)
        except ValueError as exc:
            self.source_detection_status.setText(
                translate_text("⚠ {error}").format(error=exc)
            )
            return
        descriptor = self.connector_registry.get(detected.source_type)
        if descriptor.runnable:
            message = (
                translate_text(
                    "✓ Detectado: {display} · {api}. "
                    "A descoberta de espaços e páginas acontece após a autenticação."
                ).format(display=detected.display_name, api=detected.api_name)
            )
        else:
            message = (
                translate_text(
                    "✓ URL reconhecida: {display} · {api}. "
                    "O conector desta plataforma ainda está em desenvolvimento e não fará chamadas."
                ).format(display=detected.display_name, api=detected.api_name)
            )
        self.source_detection_status.setText(message)


    def _source_from_detection(
        self,
        detected: DetectedSource,
        raw_url: str,
        name: str,
        previous: SourceConfig | None = None,
    ) -> SourceConfig:
        options = dict(previous.connector_options) if previous else {}
        options.update(
            {
                "source_url": raw_url,
                "detected_api": detected.api_name,
            }
        )
        updates: dict[str, Any] = {
            "name": name.strip() or detected.display_name,
            "source_type": detected.source_type,
            "base_url": detected.base_url,
            "space_key": detected.space_key,
            "space_name": detected.space_name,
            "root_mode": detected.root_mode,
            "root_value": detected.root_value,
            "connector_options": options,
        }
        if previous is not None:
            updates.update(
                {
                    "id": previous.id,
                    "enabled": previous.enabled,
                    "include_root": previous.include_root,
                    "selected_page_ids": list(previous.selected_page_ids),
                    "consolidation_excluded_page_ids": list(
                        previous.consolidation_excluded_page_ids
                    ),
                }
            )
        return SourceConfig.model_validate(
            (previous.model_dump() if previous else SourceConfig().model_dump())
            | updates
        )


    def _commit_source_from_form(self) -> None:
        raw_url = self.source_url_input.text().strip()
        if not raw_url:
            QMessageBox.warning(
                self,
                translate_text("URL obrigatória"),
                translate_text("Cole a URL da fonte antes de adicionar."),
            )
            return
        try:
            detected = detect_source_url(raw_url, self.connector_registry)
            row = self._editing_source_row
            previous = self.project.sources[row] if row is not None else None
            updated = self._source_from_detection(
                detected,
                raw_url,
                self.source_name_input.text(),
                previous,
            )
            if row is not None:
                self.project.sources[row] = updated
                message = translate_text("Fonte {name} alterada.").format(name=updated.name)
            elif (
                len(self.project.sources) == 1
                and not self.project.sources[0].base_url
                and self.project.sources[0].name == "Nova fonte"
            ):
                self.project.sources[0] = self._source_from_detection(
                    detected, raw_url, self.source_name_input.text(), self.project.sources[0]
                )
                row = 0
                updated = self.project.sources[0]
                message = translate_text("Fonte {name} adicionada.").format(name=updated.name)
            else:
                self.project.sources.append(updated)
                row = len(self.project.sources) - 1
                message = translate_text("Fonte {name} adicionada.").format(name=updated.name)
            self._source_added_at[updated.id] = self._source_added_at.get(
                updated.id, datetime.now().astimezone().strftime("%d/%m/%Y %H:%M")
            )
            self._editing_source_row = None
            self._refresh_source_widgets()
            self.sources_list.setCurrentRow(row)
            self._reset_source_form()
            self.mark_dirty()
            self.statusBar().showMessage(message, 3500)
        except ValueError as exc:
            QMessageBox.warning(self, translate_text("URL não reconhecida"), str(exc))


    def _edit_source_row(self, table_row: int) -> None:
        if table_row < 0 or table_row >= len(self._visible_source_rows):
            return
        project_row = self._visible_source_rows[table_row]
        source = self.project.sources[project_row]
        self._editing_source_row = project_row
        self.source_table.selectRow(table_row)
        self.source_url_input.setText(
            str(source.connector_options.get("source_url") or source.base_url)
        )
        self.source_name_input.setText(source.name)
        self.source_add_button.setText(translate_text("💾 Salvar alterações"))
        self.source_cancel_button.setEnabled(True)
        self.source_detection_status.setText(
            translate_text(
                "Editando {name}. Altere a URL ou o nome e salve para atualizar a fonte."
            ).format(name=source.name)
        )


    def _reset_source_form(self) -> None:
        self._editing_source_row = None
        self.source_url_input.clear()
        self.source_name_input.clear()
        self.source_add_button.setText(translate_text("＋ Adicionar"))
        self.source_cancel_button.setEnabled(False)
        self._preview_detected_source()


    def _cancel_source_edit(self) -> None:
        self._reset_source_form()


    def remove_selected_sources(self) -> None:
        rows = self._selected_source_rows()
        if not rows:
            self.statusBar().showMessage(
                translate_text("Selecione uma fonte para remover."), 3000
            )
            return
        names = ", ".join(self.project.sources[row].name for row in rows)
        if (
            QMessageBox.question(
                self,
                translate_text("Remover fontes"),
                translate_text("Remover {names} do projeto?").format(names=names),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        for row in sorted(rows, reverse=True):
            source = self.project.sources.pop(row)
            self.trees.pop(source.id, None)
            self.secrets.pop(source.id, None)
            self._source_added_at.pop(source.id, None)
        self._reset_source_form()
        self._refresh_source_widgets()
        self.mark_dirty()
        self.statusBar().showMessage(translate_text("Fonte(s) removida(s)."), 3000)


    def current_source(self) -> SourceConfig | None:
        row = self.sources_list.currentRow() if hasattr(self, "sources_list") else -1
        return resolve_source_by_index(self.project.sources, row)


    def source_by_combo(self, combo: QComboBox) -> SourceConfig | None:
        return resolve_source_by_combo(self.project.sources, combo)


    def _source_selected(self, row: int) -> None:
        if not 0 <= row < len(self.project.sources):
            return
        source = self.project.sources[row]
        self._loading_source_form = True
        try:
            self.src_name.setText(source.name)
            platform_index = self.src_platform.findData(source.source_type)
            self.src_platform.setCurrentIndex(platform_index)
            self.src_url.setText(source.base_url)
            self.src_space.setText(source.space_key)
            self.src_space_name.setText(source.space_name)
            index = self.src_root_mode.findData(source.root_mode)
            self.src_root_mode.setCurrentIndex(max(index, 0))
            self.src_root.setText(source.root_value)
            self.src_enabled.setChecked(source.enabled)
            self.src_include_root.setChecked(source.include_root)
            if hasattr(self, "source_url_input"):
                self.source_url_input.setText(
                    str(source.connector_options.get("source_url") or source.base_url)
                )
                self.source_name_input.setText(
                    "" if source.name == "Nova fonte" and not source.base_url else source.name
                )
            self.src_autofill_status.setText(
                translate_text(
                    "💡 Cole uma URL completa para preencher estes campos automaticamente."
                )
            )
        finally:
            self._loading_source_form = False
        self._source_platform_changed(self.src_platform.currentIndex())
        self._source_root_mode_changed()


    def _source_platform_changed(self, _index: int) -> None:
        if not hasattr(self, "src_platform") or self._loading_source_form:
            return
        source = self.current_source()
        if not source:
            return
        selected = self.src_platform.currentData()
        selected_source_type = str(selected or source.source_type)
        try:
            descriptor = self.connector_registry.get(selected_source_type)
        except ValueError:
            self.src_url.setEnabled(False)
            self.src_space.setEnabled(False)
            self.src_space_name.setEnabled(False)
            self.src_root_mode.setEnabled(False)
            self.src_root.setEnabled(False)
            self.src_include_root.setEnabled(False)
            self.src_autofill_status.setText(
                translate_text(
                    "{source_type}: Conector não registrado. Selecione uma plataforma suportada para continuar."
                ).format(source_type=selected_source_type)
            )
            return
        runnable = descriptor.runnable
        self.src_url.setEnabled(True)
        spec = descriptor.form
        self.src_space.setEnabled(spec.supports_scope)
        self.src_space_name.setEnabled(spec.supports_scope)
        self.src_root_mode.setEnabled(spec.supports_root)
        self.src_root.setEnabled(spec.supports_root)
        self.src_include_root.setEnabled(spec.supports_root)
        self.src_url_label.setText(translate_text(spec.url_label))
        self.src_url.setPlaceholderText(translate_text(spec.url_placeholder))
        self.src_space_label.setText(translate_text(spec.scope_label))
        self.src_space.setPlaceholderText(translate_text(spec.scope_placeholder))
        self.src_space_name_label.setText(translate_text(spec.scope_name_label))
        if not runnable:
            self.src_autofill_status.setText(
                translate_text(
                    "{name}: Em desenvolvimento. Nenhuma chamada será realizada."
                ).format(name=descriptor.display_name)
            )

        else:
            self.src_autofill_status.setText(translate_text(spec.help_text))


    def _autofill_source_url(self) -> None:
        if self._loading_source_form:
            return
        raw = self.src_url.text().strip()
        if not raw or ("/" not in raw.removeprefix("https://").removeprefix("http://")):
            return
        selected_source_type = str(
            self.src_platform.currentData() or "confluence_rest"
        )
        if selected_source_type != "confluence_rest":
            try:
                detected = detect_source_url(raw, self.connector_registry)
            except ValueError as exc:
                self.src_autofill_status.setText(
                    translate_text("⚠ {error}").format(error=exc)
                )
                return
            if detected.source_type != selected_source_type:
                return
            self._loading_source_form = True
            try:
                self.src_url.setText(detected.base_url)
                if detected.space_key:
                    self.src_space.setText(detected.space_key)
                if detected.space_name:
                    self.src_space_name.setText(detected.space_name)
                index = self.src_root_mode.findData(detected.root_mode)
                if index >= 0:
                    self.src_root_mode.setCurrentIndex(index)
                self.src_root.setText(detected.root_value)
            finally:
                self._loading_source_form = False
            self.src_autofill_status.setText(
                translate_text("✓ Detectado: {display} · {api}.").format(
                    display=detected.display_name,
                    api=detected.api_name,
                )
            )
            return
        try:
            parsed = parse_confluence_url(raw)
        except ValueError as exc:
            self.src_autofill_status.setText(
                translate_text("⚠ {error}").format(error=exc)
            )
            return
        self._loading_source_form = True
        try:
            self.src_url.setText(parsed.base_url)
            if parsed.space_key:
                self.src_space.setText(parsed.space_key)
            if parsed.root_mode:
                index = self.src_root_mode.findData(parsed.root_mode)
                if index >= 0:
                    self.src_root_mode.setCurrentIndex(index)
                self.src_root.setText(parsed.root_value)
        finally:
            self._loading_source_form = False
        if parsed.root_mode == "space":
            self.src_include_root.setChecked(True)
        self._source_root_mode_changed()
        self.apply_source(silent=True)
        if parsed.page_id:
            source = self.current_source()
            if source and source.id in self.connected_sources:
                self.src_autofill_status.setText(
                    translate_text(
                        "🔎 pageId {page_id} identificado. Consultando título e espaço…"
                    ).format(page_id=parsed.page_id)
                )
                self._lookup_page_details(parsed.page_id)
            else:
                self.src_autofill_status.setText(
                    translate_text(
                        "✅ pageId {page_id} identificado. Teste a conexão para "
                        "confirmar o título e o espaço."
                    ).format(page_id=parsed.page_id)
                )
        elif parsed.root_mode == "space":
            self.src_autofill_status.setText(
                translate_text(
                    "✅ Espaço {space} identificado. A árvore inteira será carregada."
                ).format(space=parsed.space_key)
            )
        elif parsed.title:
            self.src_autofill_status.setText(
                translate_text(
                    "✅ Espaço {space} e página “{title}” identificados."
                ).format(
                    space=parsed.space_key or translate_text("não informado"),
                    title=parsed.title,
                )
            )
        else:
            self.src_autofill_status.setText(
                translate_text(
                    "ℹ URL válida, mas ela não contém título nem pageId. Preencha a página raiz."
                )
            )


    def _lookup_page_details(self, page_id: str | None = None) -> None:
        source = self.current_source()
        if not source or self.page_lookup_worker is not None:
            return
        identifier = page_id or (
            self.src_root.text().strip()
            if self.src_root_mode.currentData() == "id"
            else ""
        )
        if not identifier:
            return
        lookup_source = source.model_copy(
            update={
                "base_url": self.src_url.text().strip(),
                "space_key": self.src_space.text().strip(),
                "root_mode": "id",
                "root_value": identifier,
            }
        )
        # Snapshot the extraction options and secret on the UI thread before
        # dispatching the worker. The worker thread must not read mutable UI
        # state (self.project.extraction / self.secrets) that a concurrent UI
        # action could mutate mid-fetch.
        extraction_snapshot = self.project.extraction.model_copy(deep=True)
        secret_snapshot = self.secrets.get(source.id, "")

        def work(token: CancellationToken, progress: Any, log: Any) -> dict[str, Any]:
            with ConfluenceClient(
                lookup_source,
                extraction_snapshot,
                secret=secret_snapshot,
                token=token,
                log=log,
            ) as client:
                return client.fetch_page(identifier, include_body=False)

        worker = Worker(work, token=CancellationToken())
        self.page_lookup_worker = worker

        def done(page: dict[str, Any]) -> None:
            if self.current_source() is not source:
                return
            space = page.get("space", {}) or {}
            if space.get("key"):
                self.src_space.setText(str(space["key"]))
            if space.get("name"):
                self.src_space_name.setText(str(space["name"]))
            self.apply_source(silent=True)
            self.src_autofill_status.setText(
                translate_text(
                    "✅ pageId {identifier} confirmado: “{title}”{space}"
                ).format(
                    identifier=identifier,
                    title=page.get("title", translate_text("sem título")),
                    space=(
                        translate_text(" · espaço {key}").format(key=space["key"])
                        if space.get("key")
                        else ""
                    ),
                )
            )

        def failed(error: Exception | str, _details: str) -> None:
            message = str(error)
            self.src_autofill_status.setText(
                translate_text(
                    "⚠ pageId {identifier} foi preenchido, mas título e espaço não puderam "
                    "ser consultados: {message}"
                ).format(identifier=identifier, message=message)
            )

        worker.signals.succeeded.connect(done)
        worker.signals.failed.connect(failed)
        worker.signals.finished.connect(lambda: setattr(self, "page_lookup_worker", None))
        self.thread_pool.start(worker)


    def _source_root_mode_changed(self) -> None:
        entire_space = self.src_root_mode.currentData() == "space"
        self.src_root.setEnabled(not entire_space)
        self.src_include_root.setEnabled(not entire_space)
        if entire_space:
            self.src_root.clear()
            self.src_include_root.setChecked(True)


    def add_source(self) -> None:
        self.project.sources.append(SourceConfig(name="Nova fonte"))
        self._refresh_source_widgets()
        self.sources_list.setCurrentRow(len(self.project.sources) - 1)
        self.mark_dirty()


    def duplicate_source(self) -> None:
        source = self.current_source()
        if not source:
            return
        clone = source.model_copy(deep=True)
        clone.id = uuid.uuid4().hex
        clone.name = f"{source.name} — cópia"
        clone.selected_page_ids = list(source.selected_page_ids)
        self.project.sources.append(clone)
        self._refresh_source_widgets()
        self.sources_list.setCurrentRow(len(self.project.sources) - 1)
        self.mark_dirty()


    def remove_source(self) -> None:
        source = self.current_source()
        if not source:
            return
        if (
            QMessageBox.question(
                self,
                translate_text("Remover fonte"),
                translate_text("Remover “{name}” do projeto?").format(name=source.name),
            )
            != QMessageBox.StandardButton.Yes
        ):
            return
        self.project.sources.remove(source)
        self.trees.pop(source.id, None)
        self.secrets.pop(source.id, None)
        self._refresh_source_widgets()
        self.mark_dirty()


    def export_source_profile(self) -> None:
        source = self.current_source()
        if not source:
            return
        selected, _ = QFileDialog.getSaveFileName(
            self,
            translate_text("Exportar perfil da fonte"),
            f"{source.source_slug}.json",
            translate_text("Perfil JSON (*.json)"),
        )
        if not selected:
            return
        data = source.model_dump(mode="json", exclude={"state_file"})
        data.pop("selected_page_ids", None)
        data.pop("consolidation_excluded_page_ids", None)
        Path(selected).write_text(
            json.dumps({"schema_version": 3, "source": data}, ensure_ascii=False, indent=2)
            + "\n",
            encoding="utf-8",
        )


    def import_source_profile(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            translate_text("Importar perfil da fonte"),
            "",
            translate_text("Perfil JSON (*.json)"),
        )
        if not selected:
            return
        try:
            raw = json.loads(Path(selected).read_text(encoding="utf-8"))
            data = raw.get("source", raw)
            data["id"] = uuid.uuid4().hex
            data.pop("state_file", None)
            source = SourceConfig.model_validate(data)
            self.project.sources.append(source)
            self._refresh_source_widgets()
            self.sources_list.setCurrentRow(len(self.project.sources) - 1)
            self.mark_dirty()
        except Exception as exc:
            QMessageBox.warning(self, translate_text("Perfil inválido"), str(exc))


    def apply_source(self, *, silent: bool = False) -> bool:
        source = self.current_source()
        if not source:
            return True
        try:
            selected = self.src_platform.currentData()
            selected_source_type = str(selected or source.source_type)
            try:
                descriptor = self.connector_registry.get(selected_source_type)
            except ValueError:
                descriptor = None
            source_type_changed = selected_source_type != source.source_type
            updated = source.model_copy(
                update={
                    "name": self.src_name.text().strip() or "Fonte sem nome",
                    "source_type": selected_source_type,
                    "base_url": self.src_url.text().strip(),
                    "space_key": self.src_space.text().strip(),
                    "space_name": self.src_space_name.text().strip(),
                    "root_mode": str(self.src_root_mode.currentData()),
                    "root_value": self.src_root.text().strip(),
                    "enabled": self.src_enabled.isChecked(),
                    "include_root": self.src_include_root.isChecked(),
                    "selected_page_ids": [] if source_type_changed else source.selected_page_ids,
                    "consolidation_excluded_page_ids": (
                        []
                        if source_type_changed
                        else source.consolidation_excluded_page_ids
                    ),
                    "auth_mode": (
                        AuthMode.BEARER
                        if descriptor is not None and descriptor.form.bearer_only
                        else source.auth_mode
                    ),
                }
            )
            updated = SourceConfig.model_validate(updated.model_dump())
            if source_type_changed:
                self._invalidate_source_type_state(source)
            self.project.sources[self.sources_list.currentRow()] = updated
            self._refresh_source_widgets()
            self.mark_dirty()
            if not silent:
                self.statusBar().showMessage(translate_text("Fonte atualizada."), 3000)
            return True
        except Exception as exc:
            if not silent:
                QMessageBox.warning(self, translate_text("Fonte inválida"), str(exc))
            return False


    def _invalidate_source_type_state(self, source: SourceConfig) -> None:
        """Drop runtime state that is not portable across connector types."""
        self.secrets.pop(source.id, None)
        delete_session(source)
        self.trees.pop(source.id, None)
        self.connected_sources.discard(source.id)
        self.connection_states.pop(source.id, None)
        self.project.selections = [
            item for item in self.project.selections if item.source_id != source.id
        ]
        for key in list(self.selection_store.keys_for_source(source.id)):
            source_id, container_id, document_id = key.split(":", 2)
            self.selection_store.set(source_id, container_id, document_id, False)
        self._page_render_limits = {
            key: value
            for key, value in self._page_render_limits.items()
            if key[0] != source.id
        }
        self._selection_render_limits = {
            key: value
            for key, value in self._selection_render_limits.items()
            if key[0] != source.id
        }
        self._active_page_container = None
        self._active_selection_container = None

    def _pick_local_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            translate_text("Selecionar Arquivo de Conhecimento"),
            "",
            translate_text(
                "Todos os Documentos Suportados (*.pdf *.docx *.xlsx *.pptx *.epub *.html *.txt *.md);;"
                "PDF (*.pdf);;Word (*.docx *.rtf *.odt);;Excel / Planilhas (*.xlsx *.xls *.csv *.tsv);;"
                "PowerPoint (*.pptx *.odp);;E-books (*.epub);;HTML (*.html *.htm);;Texto / Markdown (*.txt *.md *.mdx);;"
                "Imagens (*.png *.jpg *.jpeg *.webp);;Todos os Arquivos (*.*)"
            ),
        )
        if file_path:
            self.source_url_input.setText(file_path)

    def _pick_local_folder(self) -> None:
        folder_path = QFileDialog.getExistingDirectory(
            self,
            translate_text("Selecionar Pasta de Documentos"),
            "",
        )
        if folder_path:
            self.source_url_input.setText(folder_path)
