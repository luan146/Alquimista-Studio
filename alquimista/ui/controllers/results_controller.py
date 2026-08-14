from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QStatusBar,
    QWidget,
)

from ...storage import MANIFEST_NAME
from ..i18n import translate_text


class ResultsController:
    """Manages results summary formatting, metric presentation, and OS/clipboard actions."""

    def __init__(
        self,
        summary_widget: QPlainTextEdit | None = None,
        status_bar: QStatusBar | None = None,
        output_dir_getter: Callable[[], Path] | None = None,
        log_path: Path | None = None,
        metric_widgets: dict[str, Any] | None = None,
        output_path_label: QLabel | None = None,
    ) -> None:
        self.summary_widget = summary_widget
        self.status_bar = status_bar
        self.output_dir_getter = output_dir_getter or Path.cwd
        self.log_path = log_path
        self.metric_widgets = metric_widgets or {}
        self.output_path_label = output_path_label

    def refresh_results(self, last_result: dict[str, Any] | None) -> None:
        if not last_result:
            return
        result = last_result
        if "extraction" in result:
            extraction = result["extraction"]
            consolidation = result["consolidation"]
            result = {
                **extraction,
                "packages": consolidation.get("packages", 0),
                "pages_in_packages": consolidation.get("pages", 0),
                "duration_seconds": last_result.get("duration_seconds", 0),
            }
        lines = ["RESULTADO DA OPERAÇÃO", ""]
        if "counters" in result:
            lines.extend(
                [
                    f"Fontes processadas: {len(result.get('sources', []))}",
                    f"Páginas encontradas: {result.get('pages_found', 0)}",
                    f"Páginas selecionadas: {result.get('pages_selected', 0)}",
                ]
            )
            for key, value in result.get("counters", {}).items():
                lines.append(f"{key}: {value}")
            lines.append(f"Falhas: {result.get('failures', 0)}")
            if "packages" in result:
                lines.append(f"Pacotes gerados: {result.get('packages', 0)}")
            lines.append(f"Manifesto: {result.get('manifest', '')}")
        else:
            lines.extend(
                [
                    f"Pacotes gerados: {result.get('packages', 0)}",
                    f"Documentos: {result.get('pages', 0)}",
                ]
            )
        lines.extend(
            [
                f"Duração: {result.get('duration_seconds', 0)}s",
                f"Saída: {result.get('output_dir', '')}",
            ]
        )
        if self.summary_widget is not None:
            self.summary_widget.setPlainText("\n".join(lines))

        total_val = (
            result.get("pages_selected")
            or result.get("pages_found")
            or result.get("pages", 0)
        )
        if "total" in self.metric_widgets:
            self.metric_widgets["total"].setText(str(total_val))
        if "packages" in self.metric_widgets:
            self.metric_widgets["packages"].setText(
                str(result.get("packages", 0))
            )
        if "time" in self.metric_widgets:
            dur = result.get("duration_seconds", 0)
            self.metric_widgets["time"].setText(
                f"{dur:.1f}s" if isinstance(dur, (int, float)) else f"{dur}s"
            )
        if "failures" in self.metric_widgets:
            self.metric_widgets["failures"].setText(
                str(result.get("failures", 0))
            )
        if self.output_path_label is not None and result.get("output_dir"):
            self.output_path_label.setText(str(result.get("output_dir")))

    def base_path(self) -> Path:
        return self.output_dir_getter()

    def copy_report(self) -> None:
        if self.summary_widget is not None:
            QApplication.clipboard().setText(self.summary_widget.toPlainText())
            if self.status_bar is not None:
                self.status_bar.showMessage(
                    translate_text("Relatório copiado."), 3000
                )

    def open_output(self) -> None:
        path = self.base_path()
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def copy_output_path(self) -> None:
        QApplication.clipboard().setText(str(self.base_path()))
        if self.status_bar is not None:
            self.status_bar.showMessage(
                translate_text("Caminho da pasta copiado."), 3000
            )

    def open_manifest(
        self, parent: QWidget | None = None, manifest_name: str = MANIFEST_NAME
    ) -> None:
        path = self.base_path() / manifest_name
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            QMessageBox.information(
                parent,
                translate_text("Manifesto"),
                translate_text("O manifesto ainda não foi criado."),
            )

    def open_log(self, parent: QWidget | None = None) -> None:
        if self.log_path and self.log_path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.log_path)))
        else:
            QMessageBox.information(
                parent,
                translate_text("Log técnico"),
                translate_text("O log ainda não foi criado."),
            )

    def export_report(self, parent: QWidget | None = None) -> None:
        if self.summary_widget is None:
            return
        selected, _ = QFileDialog.getSaveFileName(
            parent,
            "Exportar relatório",
            "relatorio_alquimista.txt",
            "Texto (*.txt)",
        )
        if selected:
            Path(selected).write_text(
                self.summary_widget.toPlainText(), encoding="utf-8"
            )

    def choose_output(
        self, parent: QWidget | None, on_chosen: Callable[[str], None]
    ) -> None:
        selected = QFileDialog.getExistingDirectory(
            parent, "Escolher pasta da base"
        )
        if selected:
            on_chosen(selected)


__all__ = ["ResultsController"]
