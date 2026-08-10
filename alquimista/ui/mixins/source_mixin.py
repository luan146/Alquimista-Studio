import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QMessageBox,
    QPushButton,
    QTableWidgetItem,
)

from ...client import ConfluenceClient
from ...confluence_url import parse_confluence_url
from ...models import AuthMode, SourceConfig, now_iso
from ...runtime import CancellationToken
from ...source_detection import DetectedSource, detect_source_url
from ..connector_forms import form_spec
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
    mark_dirty: Any
    thread_pool: Any
    statusBar: Any
    worker: Any
    page_lookup_worker: "Worker | None"
    _editing_source_row: int | None
    _source_added_at: dict[str, str]
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
            descriptor = self.connector_registry.get(source.source_type)
            api_label = f"{descriptor.display_name} · {descriptor.integration_name}"
            self.source_table.setItem(table_row, 3, QTableWidgetItem(api_label))
            added_at = self._source_added_at.get(source.id, now_iso())
            self._source_added_at.setdefault(source.id, added_at)
            self.source_table.setItem(table_row, 4, QTableWidgetItem(added_at))

            menu = QPushButton("⋮")
            menu.setToolTip("Alterar nome, URL ou configurações da fonte")
            menu.setAccessibleName(f"Alterar fonte {source.name}")
            menu.clicked.connect(
                lambda _checked=False, row=table_row: self._edit_source_row(row)
            )
            self.source_table.setCellWidget(table_row, 5, menu)
            self.source_table.setRowHeight(table_row, 44)

        self.source_count_label.setText(f"{len(visible_rows)} itens")
        self.sources_empty_label.setVisible(not visible_rows)


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
                "A plataforma, a API e os detalhes iniciais serão identificados pela URL."
            )
            return
        try:
            detected = detect_source_url(raw)
        except ValueError as exc:
            self.source_detection_status.setText(f"⚠ {exc}")
            return
        descriptor = self.connector_registry.get(detected.source_type)
        if descriptor.operational:
            message = (
                f"✓ Detectado: {detected.display_name} · {detected.api_name}. "
                "A descoberta de espaços e páginas acontece após a autenticação."
            )
        else:
            message = (
                f"✓ URL reconhecida: {detected.display_name} · {detected.api_name}. "
                "O conector desta plataforma ainda está em desenvolvimento e não fará chamadas."
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
            QMessageBox.warning(self, "URL obrigatória", "Cole a URL da fonte antes de adicionar.")
            return
        try:
            detected = detect_source_url(raw_url)
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
                message = f"Fonte {updated.name} alterada."
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
                message = f"Fonte {updated.name} adicionada."
            else:
                self.project.sources.append(updated)
                row = len(self.project.sources) - 1
                message = f"Fonte {updated.name} adicionada."
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
            QMessageBox.warning(self, "URL não reconhecida", str(exc))


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
        self.source_add_button.setText("💾 Salvar alterações")
        self.source_cancel_button.setEnabled(True)
        self.source_detection_status.setText(
            f"Editando {source.name}. Altere a URL ou o nome e salve para atualizar a fonte."
        )


    def _reset_source_form(self) -> None:
        self._editing_source_row = None
        self.source_url_input.clear()
        self.source_name_input.clear()
        self.source_add_button.setText("＋ Adicionar")
        self.source_cancel_button.setEnabled(False)
        self._preview_detected_source()


    def _cancel_source_edit(self) -> None:
        self._reset_source_form()


    def remove_selected_sources(self) -> None:
        rows = self._selected_source_rows()
        if not rows:
            self.statusBar().showMessage("Selecione uma fonte para remover.", 3000)
            return
        names = ", ".join(self.project.sources[row].name for row in rows)
        if (
            QMessageBox.question(
                self,
                "Remover fontes",
                f"Remover {names} do projeto?",
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
        self.statusBar().showMessage("Fonte(s) removida(s).", 3000)


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
            self.src_platform.setCurrentIndex(max(platform_index, 0))
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
                "💡 Cole uma URL completa para preencher estes campos automaticamente."
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
        source.source_type = str(self.src_platform.currentData() or "confluence_rest")
        descriptor = self.connector_registry.get(source.source_type)
        implemented = descriptor.operational
        self.src_url.setEnabled(implemented)
        confluence = implemented and source.source_type == "confluence_rest"
        gitbook = implemented and source.source_type == "gitbook_api"
        zendesk = implemented and source.source_type == "zendesk_guide"
        spec = form_spec(source.source_type)
        self.src_space.setEnabled(implemented and spec.supports_scope)
        self.src_space_name.setEnabled(implemented and spec.supports_scope)
        self.src_root_mode.setEnabled(implemented and spec.supports_root)
        self.src_root.setEnabled(implemented and spec.supports_root)
        self.src_include_root.setEnabled(implemented and spec.supports_root)
        if spec.bearer_only and source.auth_mode != AuthMode.BEARER:
            source.auth_mode = AuthMode.BEARER
        if gitbook:
            self.src_url_label.setText("URL da API GitBook (opcional)")
            self.src_url.setPlaceholderText("https://api.gitbook.com/v1")
            self.src_space_label.setText("ID da organização GitBook")
            self.src_space.setPlaceholderText("organizationId")
            self.src_space_name_label.setText("Nome da organização (opcional)")
            self.src_root_mode.setCurrentIndex(self.src_root_mode.findData("space"))
            self.src_autofill_status.setText(
                "GitBook usa o ID da organização e um Personal Access Token; o conteúdo é descoberto pela API oficial."
            )
        elif zendesk:
            if source.auth_mode != AuthMode.BEARER:
                source.auth_mode = AuthMode.BEARER
            self.src_url_label.setText("URL da API Zendesk (opcional)")
            self.src_url.setPlaceholderText("https://subdominio.zendesk.com/api/v2")
            self.src_space_label.setText("Subdomínio Zendesk")
            self.src_space.setPlaceholderText("subdominio")
            self.src_space_name_label.setText("Locale (opcional)")
            self.src_autofill_status.setText(
                "Zendesk Guide usa um access token OAuth em modo Bearer e acessa somente o Help Center."
            )
        elif confluence:
            self.src_url_label.setText("URL do Confluence")
            self.src_url.setPlaceholderText("Cole a URL completa da página do Confluence")
            self.src_space_label.setText("Chave do espaço")
            self.src_space.setPlaceholderText("")
            self.src_space_name_label.setText("Nome do espaço")
        if implemented:
            self.src_autofill_status.setText(
                f"Integração: {descriptor.integration_name}. As capacidades serão descobertas após a conexão."
            )
        else:
            self.src_autofill_status.setText(
                f"{descriptor.display_name}: Em desenvolvimento. Nenhuma chamada será realizada."
            )

        if implemented:
            self.src_url_label.setText(spec.url_label)
            self.src_url.setPlaceholderText(spec.url_placeholder)
            self.src_space_label.setText(spec.scope_label)
            self.src_space.setPlaceholderText(spec.scope_placeholder)
            self.src_space_name_label.setText(spec.scope_name_label)
            self.src_autofill_status.setText(spec.help_text)


    def _autofill_source_url(self) -> None:
        if self._loading_source_form:
            return
        raw = self.src_url.text().strip()
        if not raw or ("/" not in raw.removeprefix("https://").removeprefix("http://")):
            return
        try:
            parsed = parse_confluence_url(raw)
        except ValueError as exc:
            self.src_autofill_status.setText(f"⚠ {exc}")
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
                    f"🔎 pageId {parsed.page_id} identificado. Consultando título e espaço…"
                )
                self._lookup_page_details(parsed.page_id)
            else:
                self.src_autofill_status.setText(
                    f"✅ pageId {parsed.page_id} identificado. Teste a conexão para "
                    "confirmar o título e o espaço."
                )
        elif parsed.root_mode == "space":
            self.src_autofill_status.setText(
                f"✅ Espaço {parsed.space_key} identificado. A árvore inteira será carregada."
            )
        elif parsed.title:
            self.src_autofill_status.setText(
                f"✅ Espaço {parsed.space_key or 'não informado'} e página "
                f"“{parsed.title}” identificados."
            )
        else:
            self.src_autofill_status.setText(
                "ℹ URL válida, mas ela não contém título nem pageId. Preencha a página raiz."
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
                f"✅ pageId {identifier} confirmado: “{page.get('title', 'sem título')}”"
                + (f" · espaço {space['key']}" if space.get("key") else "")
            )

        def failed(message: str, _details: str) -> None:
            self.src_autofill_status.setText(
                f"⚠ pageId {identifier} foi preenchido, mas título e espaço não puderam "
                f"ser consultados: {message}"
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
                self, "Remover fonte", f"Remover “{source.name}” do projeto?"
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
            "Exportar perfil da fonte",
            f"{source.source_slug}.json",
            "Perfil JSON (*.json)",
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
            self, "Importar perfil da fonte", "", "Perfil JSON (*.json)"
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
            QMessageBox.warning(self, "Perfil inválido", str(exc))


    def apply_source(self, *, silent: bool = False) -> bool:
        source = self.current_source()
        if not source:
            return True
        try:
            updated = source.model_copy(
                update={
                    "name": self.src_name.text().strip() or "Fonte sem nome",
                    "source_type": str(self.src_platform.currentData() or "confluence_rest"),
                    "base_url": self.src_url.text().strip(),
                    "space_key": self.src_space.text().strip(),
                    "space_name": self.src_space_name.text().strip(),
                    "root_mode": str(self.src_root_mode.currentData()),
                    "root_value": self.src_root.text().strip(),
                    "enabled": self.src_enabled.isChecked(),
                    "include_root": self.src_include_root.isChecked(),
                }
            )
            updated = SourceConfig.model_validate(updated.model_dump())
            self.project.sources[self.sources_list.currentRow()] = updated
            self._refresh_source_widgets()
            self.mark_dirty()
            if not silent:
                self.statusBar().showMessage("Fonte atualizada.", 3000)
            return True
        except Exception as exc:
            if not silent:
                QMessageBox.warning(self, "Fonte inválida", str(exc))
            return False



