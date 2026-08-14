from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSignalBlocker, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QWidget,
)

from ...connectors.confluence_parser import ConfluenceDocumentParser
from ...markdown import KnowledgeDocumentRenderer, sample_page
from ...models import MarkdownOptions, SourceConfig
from ..i18n import translate_text


class PreviewController:
    """Controls Markdown options sync, presets, debounce preview, and output summary."""

    def __init__(
        self,
        md_controls: dict[str, QWidget],
        preview_mode_combo: QComboBox | None = None,
        preview_editor: QPlainTextEdit | None = None,
        preview_timer: QTimer | None = None,
        extraction_summary_label: Any | None = None,
        output_path_status_label: Any | None = None,
        output_structure_label: Any | None = None,
        output_dir_input: QLineEdit | None = None,
        output_subfolder_checkbox: QCheckBox | None = None,
    ) -> None:
        self.md_controls = md_controls
        self.preview_mode_combo = preview_mode_combo
        self.preview_editor = preview_editor
        self.preview_timer = preview_timer
        self.extraction_summary_label = extraction_summary_label
        self.output_path_status_label = output_path_status_label
        self.output_structure_label = output_structure_label
        self.output_dir_input = output_dir_input
        self.output_subfolder_checkbox = output_subfolder_checkbox
        self._preview_raw = ""

    def load_markdown_controls(self, options: MarkdownOptions) -> None:
        for key, control in self.md_controls.items():
            value = getattr(options, key, None)
            if value is None:
                continue
            blocker = QSignalBlocker(control)
            if isinstance(control, QCheckBox):
                control.setChecked(bool(value))
            elif isinstance(control, QComboBox):
                index = control.findData(str(value))
                if index >= 0:
                    control.setCurrentIndex(index)
                else:
                    control.setCurrentText(str(value))
            elif isinstance(control, QSpinBox):
                control.setValue(int(value))
            elif isinstance(control, QLineEdit):
                control.setText(str(value))
            del blocker

    def sync_markdown_controls(
        self, current_options: MarkdownOptions
    ) -> MarkdownOptions:
        data = current_options.model_dump()
        for key, control in self.md_controls.items():
            if isinstance(control, QCheckBox):
                data[key] = control.isChecked()
            elif isinstance(control, QComboBox):
                data[key] = (
                    control.currentData()
                    if control.currentData() is not None
                    else control.currentText()
                )
            elif isinstance(control, QSpinBox):
                data[key] = control.value()
            elif isinstance(control, QLineEdit):
                data[key] = control.text()
        return MarkdownOptions.model_validate(data)

    def apply_preset(
        self, name: str, on_dirty: Callable[[], None] | None = None
    ) -> MarkdownOptions:
        options = MarkdownOptions.preset(name)
        self.load_markdown_controls(options)
        if on_dirty is not None:
            on_dirty()
        return options

    def schedule_preview(
        self, on_dirty: Callable[[], None] | None = None
    ) -> None:
        if self.preview_timer is not None:
            self.preview_timer.start()
        if on_dirty is not None:
            on_dirty()

    def update_preview(
        self,
        sources: list[SourceConfig],
        options: MarkdownOptions,
    ) -> str:
        try:
            # Declarative source selection: active enabled source or first available
            configured_source = next(
                (
                    source
                    for source in sources
                    if getattr(source, "enabled", True)
                ),
                None,
            ) or (sources[0] if sources else None)
            source = configured_source or SourceConfig(
                name=translate_text("Exemplo"),
                base_url="https://example.test",
                space_key="EXEMPLO",
                space_name=translate_text("Espaço de exemplo"),
            )
            source = source.model_copy(
                update={
                    "base_url": source.base_url or "https://example.test",
                    "space_key": source.space_key or "EXEMPLO",
                    "space_name": source.space_name
                    or translate_text("Espaço de exemplo"),
                }
            )
            page = sample_page(translate_text)
            page["space"] = {
                "key": source.space_key,
                "name": source.space_name,
            }
            document = ConfluenceDocumentParser(source, options).parse(page)
            renderer = KnowledgeDocumentRenderer(options)
            prepared = renderer.prepare(document, source)
            self._preview_raw = renderer.render_prepared(
                prepared,
                "2026-07-26T15:00:00-03:00",
                "preview",
            )
            self.render_preview_mode()
            return self._preview_raw
        except Exception as exc:
            error_msg = f"Não foi possível gerar a prévia:\n{exc}"
            if self.preview_editor is not None:
                self.preview_editor.setPlainText(error_msg)
            return error_msg

    def render_preview_mode(self) -> None:
        if self.preview_editor is None:
            return
        reading = (
            self.preview_mode_combo.currentData() == "reading"
            if self.preview_mode_combo is not None
            else False
        )
        if reading:
            self.preview_editor.setMarkdown(self._preview_raw)
        else:
            self.preview_editor.setPlainText(self._preview_raw)

    def update_extraction_summary(
        self, sources: list[SourceConfig], output_dir: str
    ) -> None:
        if self.extraction_summary_label is None:
            return
        active = [source for source in sources if source.enabled]
        selected = sum(len(source.selected_page_ids) for source in active)
        self.extraction_summary_label.setText(
            translate_text(
                "🔌 {sources} fontes ativas    •    📄 {selected} páginas selecionadas\n"
                "📁 Saída: {output}\n"
                "🛡 A versão anterior será preservada se uma atualização falhar."
            ).format(
                sources=len(active),
                selected=selected,
                output=output_dir,
            )
        )

    def update_output_preview(
        self,
        output_dir_text: str,
        pages_subdir: str,
        consolidation_subdir: str,
        use_subfolder: bool = False,
    ) -> None:
        if self.output_path_status_label is None:
            return
        raw = output_dir_text.strip()
        if not raw:
            self.output_path_status_label.setText(
                translate_text(
                    "Aguardando uma pasta. Use “Escolher pasta” para evitar erros de digitação."
                )
            )
            if self.output_structure_label is not None:
                self.output_structure_label.setText("")
            return
        path = Path(raw).expanduser()
        nearest = path if path.exists() else path.parent
        writable = nearest.exists() and os.access(nearest, os.W_OK)
        if writable:
            try:
                free_gb = shutil.disk_usage(nearest).free / (1024**3)
                self.output_path_status_label.setText(
                    translate_text(
                        "Pasta disponível para gravação · {free:.1f} GB livres"
                    ).format(free=free_gb)
                )
            except OSError:
                self.output_path_status_label.setText(
                    translate_text("Pasta disponível para gravação.")
                )
        else:
            self.output_path_status_label.setText(
                translate_text(
                    "Não foi possível confirmar permissão de gravação. Escolha outra pasta "
                    "ou verifique o acesso no Windows."
                )
            )
        root = path.name or "ALQuimista"
        execution = "Extracao-AAAA-MM-DD" if use_subfolder else root
        if self.output_structure_label is not None:
            self.output_structure_label.setText(
                translate_text(
                    "Estrutura prevista\n"
                    "{execution}\n"
                    "  ├─ {pages_subdir}  (arquivos Markdown individuais)\n"
                    "  ├─ {output_subdir}  (pacotes consolidados)\n"
                    "  ├─ manifesto_alquimista.json\n"
                    "  └─ relatorio_execucao.json"
                ).format(
                    execution=execution,
                    pages_subdir=pages_subdir,
                    output_subdir=consolidation_subdir,
                )
            )


__all__ = ["PreviewController"]
