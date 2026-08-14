from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from PySide6.QtCore import QSignalBlocker
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from ...models import ConsolidationOptions, ProjectConfig, SourceConfig
from ...runtime import CancellationToken
from ...services import ConsolidationService
from ..i18n import translate_text


class ConsolidationController:
    """Controls consolidation configuration, depth computation, summary, and preview/run dispatch."""

    def __init__(
        self,
        group_combo: QComboBox | None = None,
        pages_spin: QSpinBox | None = None,
        chars_spin: QSpinBox | None = None,
        depth_spin: QSpinBox | None = None,
        depth_choice_combo: QComboBox | None = None,
        prefix_input: QLineEdit | None = None,
        hierarchy_checkbox: QCheckBox | None = None,
        summary_label: QLabel | None = None,
        group_help_label: QLabel | None = None,
        depth_example_label: QLabel | None = None,
        depth_preview_label: QLabel | None = None,
        filename_preview_label: QLabel | None = None,
        preview_status_label: QLabel | None = None,
        package_table: QTableWidget | None = None,
        stat_labels: dict[str, QLabel] | None = None,
        distribution_title: QLabel | None = None,
        preview_empty_widget: QWidget | None = None,
        preview_button: QPushButton | None = None,
        generate_button: QPushButton | None = None,
    ) -> None:
        self.group_combo = group_combo
        self.pages_spin = pages_spin
        self.chars_spin = chars_spin
        self.depth_spin = depth_spin
        self.depth_choice_combo = depth_choice_combo
        self.prefix_input = prefix_input
        self.hierarchy_checkbox = hierarchy_checkbox
        self.summary_label = summary_label
        self.group_help_label = group_help_label
        self.depth_example_label = depth_example_label
        self.depth_preview_label = depth_preview_label
        self.filename_preview_label = filename_preview_label
        self.preview_status_label = preview_status_label
        self.package_table = package_table
        self.stat_labels = stat_labels or {}
        self.distribution_title = distribution_title
        self.preview_empty_widget = preview_empty_widget
        self.preview_button = preview_button
        self.generate_button = generate_button

    def update_action_availability(
        self, project: ProjectConfig, worker_running: bool = False
    ) -> None:
        active = [source for source in project.sources if source.enabled]
        has_selection = any(
            project.selected_keys_for(source.id) for source in active
        )
        ready = has_selection and not worker_running
        if self.preview_button is not None:
            self.preview_button.setEnabled(ready)
        if self.generate_button is not None:
            self.generate_button.setEnabled(ready)

    def sync_ui(
        self,
        options: ConsolidationOptions,
        sources: list[SourceConfig],
        trees: dict[str, Any],
        last_preview: list[dict[str, Any]],
    ) -> None:
        if self.group_combo is None:
            return
        index = self.group_combo.findData(options.grouping)
        self.group_combo.setCurrentIndex(max(index, 0))
        if self.pages_spin is not None:
            self.pages_spin.setValue(options.max_pages)
        if self.chars_spin is not None:
            self.chars_spin.setValue(options.max_chars)
        if self.depth_spin is not None:
            self.depth_spin.setValue(options.module_depth)
        if self.depth_choice_combo is not None:
            depth_index = self.depth_choice_combo.findData(options.module_depth)
            if depth_index >= 0:
                blocker = QSignalBlocker(self.depth_choice_combo)
                self.depth_choice_combo.setCurrentIndex(depth_index)
                del blocker
        if self.prefix_input is not None:
            self.prefix_input.setText(options.filename_prefix)
        if self.hierarchy_checkbox is not None:
            self.hierarchy_checkbox.setChecked(
                options.include_hierarchy_headings
            )
        self.update_summary(sources, trees, last_preview)

    def sync_controls(
        self, current_options: ConsolidationOptions
    ) -> ConsolidationOptions:
        if self.group_combo is None:
            return current_options
        current_options.grouping = cast(
            Any, str(self.group_combo.currentData())
        )
        if self.pages_spin is not None:
            current_options.max_pages = self.pages_spin.value()
        if self.chars_spin is not None:
            current_options.max_chars = self.chars_spin.value()
        if self.depth_spin is not None:
            depth = self.depth_spin.value()
            if self.depth_choice_combo is not None:
                depth_index = self.depth_choice_combo.findData(depth)
                if (
                    depth_index >= 0
                    and self.depth_choice_combo.currentIndex() != depth_index
                ):
                    blocker = QSignalBlocker(self.depth_choice_combo)
                    self.depth_choice_combo.setCurrentIndex(depth_index)
                    del blocker
            current_options.module_depth = depth
        if self.prefix_input is not None:
            current_options.filename_prefix = self.prefix_input.text()
        if self.hierarchy_checkbox is not None:
            current_options.include_hierarchy_headings = (
                self.hierarchy_checkbox.isChecked()
            )
        return current_options

    def depth_choice_changed(
        self,
        sources: list[SourceConfig],
        trees: dict[str, Any],
        last_preview: list[dict[str, Any]],
    ) -> None:
        if self.depth_choice_combo is None or self.depth_spin is None:
            return
        value = self.depth_choice_combo.currentData()
        if value is None:
            return
        blocker = QSignalBlocker(self.depth_spin)
        self.depth_spin.setValue(int(value))
        del blocker
        self.update_summary(sources, trees, last_preview)
        self.mark_preview_stale(last_preview)

    def example_paths(
        self,
        sources: list[SourceConfig],
        trees: dict[str, Any],
        tree_pages_fn: Callable[..., list[dict[str, Any]]],
        limit: int = 6,
    ) -> list[list[str]]:
        examples: list[list[str]] = []
        for source in sources:
            if not source.enabled:
                continue
            data = trees.get(source.id) or {}
            selected_ids = set(source.selected_page_ids)
            pages = tree_pages_fn(data)
            for page in pages:
                page_id = str(page.get("id", ""))
                if selected_ids and page_id not in selected_ids:
                    continue
                path = [
                    str(part)
                    for part in page.get("path", []) or []
                    if str(part).strip()
                ]
                if not path:
                    ancestors = page.get("ancestors", []) or []
                    path = [
                        str(ancestor.get("title", ""))
                        for ancestor in ancestors
                        if str(ancestor.get("title", "")).strip()
                    ]
                    path.append(str(page.get("title", "Sem título")))
                if len(path) > 1 and path[0] == str(
                    (page.get("space") or {}).get("name", "")
                ):
                    path = path[1:]
                if path not in examples:
                    examples.append(path)
                if len(examples) >= limit:
                    return examples
        if examples:
            return examples
        return [
            [
                translate_text("Acesso ao Sistema"),
                translate_text("Barra de Cabeçalho"),
                translate_text("Login"),
            ],
            [
                translate_text("Acesso ao Sistema"),
                translate_text("Barra de Cabeçalho"),
                translate_text("Dashboard"),
            ],
            [
                translate_text("Cadastros"),
                translate_text("Clientes"),
                translate_text("Novo cliente"),
            ],
        ][:limit]

    def update_depth_examples(
        self,
        paths: list[list[str]],
    ) -> None:
        if self.depth_choice_combo is None or self.depth_example_label is None:
            return
        level = int(
            self.depth_choice_combo.currentData()
            or (self.depth_spin.value() if self.depth_spin else 1)
        )
        lines = []
        for path in paths[:4]:
            hierarchy = path[:-1] or path[:1]
            group = " › ".join(hierarchy[:level])
            lines.append(f"• {group}  →  {path[-1]}")
        self.depth_example_label.setText(
            translate_text(
                "Exemplo no nível {level}: os pacotes serão agrupados por "
                "{level} nível(is) da árvore.\n{lines}"
            ).format(level=level, lines="\n".join(lines))
        )
        if self.depth_preview_label is not None:
            self.depth_preview_label.setText(
                translate_text("Como ficará no nível {level}:\n{lines}").format(
                    level=level, lines="\n".join(lines)
                )
            )

    def update_summary(
        self,
        sources: list[SourceConfig],
        trees: dict[str, Any],
        last_preview: list[dict[str, Any]],
        tree_pages_fn: Callable[..., list[dict[str, Any]]] | None = None,
    ) -> None:
        if self.summary_label is None or self.group_combo is None:
            return
        help_text = {
            "module": translate_text(
                "Separa os pacotes pelos módulos da árvore. Use a profundidade abaixo "
                "para escolher quantos níveis entram em cada grupo."
            ),
            "module_submodule": translate_text(
                "Separa pelo primeiro e segundo níveis da árvore, sem depender do campo "
                "de profundidade."
            ),
            "source_module": translate_text(
                "Separa por fonte e primeiro módulo; útil para várias fontes."
            ),
        }.get(
            str(self.group_combo.currentData()),
            translate_text(
                "Define quais páginas ficam juntas e como os arquivos serão distribuídos."
            ),
        )
        if self.group_help_label is not None:
            self.group_help_label.setText(help_text)
        selected = sum(
            len(source.selected_page_ids)
            for source in sources
            if source.enabled
        )
        prefix = (
            self.prefix_input.text().strip() if self.prefix_input else ""
        ) or translate_text("pacote")
        estimate = len(last_preview)
        estimate_text = (
            str(estimate) if estimate else translate_text("calculada na prévia")
        )
        if self.filename_preview_label is not None:
            self.filename_preview_label.setText(
                translate_text(
                    "Exemplo de arquivo: {prefix}-01.md, {prefix}-02.md"
                ).format(prefix=prefix)
            )
        pages_val = self.pages_spin.value() if self.pages_spin else 50
        chars_val = self.chars_spin.value() if self.chars_spin else 150000
        depth_val = self.depth_spin.value() if self.depth_spin else 1
        self.summary_label.setText(
            translate_text(
                "📋 Resumo antes de gerar: {selected} páginas · {group} · "
                "até {pages} páginas · até {chars:,} caracteres · profundidade {depth} · "
                "saída Markdown (.md) · quantidade de arquivos: {estimate}"
            )
            .format(
                selected=selected,
                group=self.group_combo.currentText(),
                pages=pages_val,
                chars=chars_val,
                depth=depth_val,
                estimate=estimate_text,
            )
            .replace(",", ".")
        )
        if tree_pages_fn is not None:
            paths = self.example_paths(sources, trees, tree_pages_fn)
            self.update_depth_examples(paths)

    def mark_preview_stale(
        self, last_preview: list[dict[str, Any]] | None
    ) -> None:
        if self.preview_status_label is None or not last_preview:
            return
        self.preview_status_label.setText(
            translate_text("○ Regras alteradas · atualize a prévia")
        )
        self.preview_status_label.setProperty("stale", True)
        self.preview_status_label.style().unpolish(self.preview_status_label)
        self.preview_status_label.style().polish(self.preview_status_label)

    def render_preview(self, preview: list[dict[str, Any]]) -> None:
        groups: dict[str, dict[str, int]] = {}
        total_pages = 0
        total_chars = 0
        oversized = 0
        for item in preview:
            group = str(item.get("group") or "Sem grupo")
            summary = groups.setdefault(
                group, {"packages": 0, "pages": 0, "characters": 0}
            )
            summary["packages"] += 1
            summary["pages"] += int(item.get("pages", 0))
            summary["characters"] += int(item.get("characters", 0))
            total_pages += int(item.get("pages", 0))
            total_chars += int(item.get("characters", 0))
            oversized += int(bool(item.get("oversized")))

        if self.package_table is not None:
            self.package_table.setRowCount(len(groups))
            for row, (group, values) in enumerate(groups.items(), 1):
                cells = [
                    str(row),
                    group,
                    str(values["packages"]),
                    str(values["pages"]),
                    f"{values['characters']:,}".replace(",", "."),
                ]
                for column, value in enumerate(cells):
                    self.package_table.setItem(
                        row - 1, column, QTableWidgetItem(value)
                    )

        package_count = len(preview)
        if "packages" in self.stat_labels:
            self.stat_labels["packages"].setText(str(package_count))
        if "pages" in self.stat_labels:
            self.stat_labels["pages"].setText(
                f"{total_pages:,}".replace(",", ".")
            )
        if "characters" in self.stat_labels:
            self.stat_labels["characters"].setText(
                f"{total_chars:,}".replace(",", ".")
            )
        if "average" in self.stat_labels:
            average = round(total_pages / package_count) if package_count else 0
            self.stat_labels["average"].setText(str(average))
        if self.distribution_title is not None:
            self.distribution_title.setText(
                translate_text(
                    "Distribuição por grupo ({count} grupos)"
                ).format(count=len(groups))
            )
        if self.package_table is not None:
            self.package_table.setVisible(bool(groups))
        if self.preview_empty_widget is not None:
            self.preview_empty_widget.setVisible(not bool(groups))
        if self.preview_status_label is not None:
            if oversized:
                self.preview_status_label.setText(
                    translate_text(
                        "⚠  Prévia atualizada · {count} pacote(s) acima do limite"
                    ).format(count=oversized)
                )
            else:
                self.preview_status_label.setText(
                    translate_text("● Prévia atualizada agora")
                )
            self.preview_status_label.setProperty("stale", False)
            self.preview_status_label.style().unpolish(
                self.preview_status_label
            )
            self.preview_status_label.style().polish(self.preview_status_label)

    def preview_consolidation(
        self,
        snapshot: ProjectConfig,
        project_dir: Path,
        worker_starter: Callable[[Any, Any], None],
        on_done: Callable[[list[dict[str, Any]]], None],
    ) -> None:
        def work(
            token: CancellationToken, progress: Any, log: Any
        ) -> list[dict[str, Any]]:
            progress(0, 1, "Calculando prévia")
            preview = ConsolidationService(
                snapshot,
                project_dir,
                token=token,
                log=log,
            ).preview()
            progress(1, 1, "Prévia concluída")
            return preview

        worker_starter(work, on_done)

    def run_consolidation(
        self,
        snapshot: ProjectConfig,
        project_dir: Path,
        worker_starter: Callable[[Any, Any], None],
        on_done: Callable[[dict[str, Any]], None],
    ) -> None:
        def work(
            token: CancellationToken, progress: Any, log: Any
        ) -> dict[str, Any]:
            return ConsolidationService(
                snapshot,
                project_dir,
                token=token,
                log=log,
                progress=progress,
            ).run()

        worker_starter(work, on_done)


__all__ = ["ConsolidationController"]
