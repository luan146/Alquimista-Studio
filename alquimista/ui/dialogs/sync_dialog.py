from __future__ import annotations

from typing import Any

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...runtime import CancellationToken
from ...services.sync import (
    IncrementalSyncService,
    SyncItemAction,
    SyncOptions,
    SyncPlan,
    SyncReport,
    SyncScope,
)
from ..components import button


class _PlanWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    log_message = Signal(str)

    def __init__(
        self,
        service: IncrementalSyncService,
        runtimes: list[Any],
        scope: SyncScope,
        target_source_id: str | None,
        token: CancellationToken,
    ) -> None:
        super().__init__()
        self.service = service
        self.runtimes = runtimes
        self.scope = scope
        self.target_source_id = target_source_id
        self.token = token

    def run(self) -> None:
        try:
            self.service.log = lambda msg: self.log_message.emit(str(msg))
            self.service.token = self.token
            plan = self.service.plan_sync(
                self.runtimes, scope=self.scope, target_source_id=self.target_source_id
            )
            self.finished.emit(plan)
        except Exception as exc:
            self.failed.emit(str(exc))


class _ApplyWorker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int, str)
    log_message = Signal(str)

    def __init__(
        self,
        service: IncrementalSyncService,
        plan: SyncPlan,
        runtimes: list[Any],
        options: SyncOptions,
        token: CancellationToken,
    ) -> None:
        super().__init__()
        self.service = service
        self.plan = plan
        self.runtimes = runtimes
        self.options = options
        self.token = token

    def run(self) -> None:
        try:
            self.service.log = lambda msg: self.log_message.emit(str(msg))
            self.service.progress = lambda done, total, item: self.progress.emit(
                int(done), int(total), str(item)
            )
            self.service.token = self.token
            report = self.service.apply_sync(
                self.plan, self.runtimes, options=self.options
            )
            self.finished.emit(report)
        except Exception as exc:
            self.failed.emit(str(exc))


class SyncPreviewDialog(QDialog):
    """Interactive preview and execution dialog for Incremental Synchronization."""

    def __init__(
        self,
        parent: QWidget | None,
        service: IncrementalSyncService,
        runtimes: list[Any],
        *,
        scope: SyncScope = SyncScope.SOURCE,
        target_source_id: str | None = None,
        source_name: str = "",
    ) -> None:
        super().__init__(parent)
        self.service = service
        self.runtimes = runtimes
        self.scope = scope
        self.target_source_id = target_source_id
        self.source_name = source_name
        self.token = CancellationToken()
        self.plan: SyncPlan | None = None
        self.report: SyncReport | None = None
        self._thread: QThread | None = None
        self._worker: QObject | None = None

        title_suffix = f" — {source_name}" if source_name else ""
        self.setWindowTitle(f"Sincronização Incremental{title_suffix}")
        self.resize(780, 560)
        self.setMinimumSize(640, 440)
        self._setup_ui()
        self._start_planning()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Header
        header_row = QHBoxLayout()
        header_title = QLabel("Prévia de Mudanças")
        header_title.setStyleSheet("font-size: 14pt; font-weight: 700;")
        header_row.addWidget(header_title)
        header_row.addStretch()
        self.scope_badge = QLabel(f"Escopo: {self.scope.value.upper()}")
        self.scope_badge.setStyleSheet(
            "background: rgba(66, 184, 190, 0.15); color: #42B8BE; "
            "padding: 4px 10px; border-radius: 4px; font-weight: 600;"
        )
        header_row.addWidget(self.scope_badge)
        main_layout.addLayout(header_row)

        # Summary Cards
        summary_row = QHBoxLayout()
        summary_row.setSpacing(10)

        def make_stat_card(label: str, color: str) -> tuple[QFrame, QLabel, QLabel]:
            frame = QFrame()
            frame.setObjectName("statCard")
            frame.setStyleSheet(
                f"QFrame#statCard {{ background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.08); "
                f"border-radius: 8px; padding: 8px; }} QLabel {{ color: {color}; }}"
            )
            vbox = QVBoxLayout(frame)
            vbox.setContentsMargins(10, 8, 10, 8)
            vbox.setSpacing(2)
            val = QLabel("—")
            val.setStyleSheet(f"font-size: 16pt; font-weight: 700; color: {color};")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl = QLabel(label)
            lbl.setStyleSheet("font-size: 9pt; opacity: 0.8;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            vbox.addWidget(val)
            vbox.addWidget(lbl)
            return frame, val, lbl

        card_new, self.val_new, _ = make_stat_card("Novos (+)", "#4CAF50")
        card_upd, self.val_upd, _ = make_stat_card("Alterados (~)", "#FFC107")
        card_rem, self.val_rem, _ = make_stat_card("Removidos (-)", "#F44336")
        card_unc, self.val_unc, _ = make_stat_card("Inalterados (=)", "#9E9E9E")

        summary_row.addWidget(card_new)
        summary_row.addWidget(card_upd)
        summary_row.addWidget(card_rem)
        summary_row.addWidget(card_unc)
        main_layout.addLayout(summary_row)

        # Table of items
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Status", "Documento", "Contêiner", "Detalhes"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        main_layout.addWidget(self.table, 1)

        # Options
        options_row = QHBoxLayout()
        self.chk_delete_files = QCheckBox("Excluir arquivos locais de documentos removidos na fonte")
        self.chk_delete_files.setChecked(True)
        self.chk_consolidate = QCheckBox("Atualizar consolidação de pacotes ao concluir")
        self.chk_consolidate.setChecked(True)
        options_row.addWidget(self.chk_delete_files)
        options_row.addWidget(self.chk_consolidate)
        options_row.addStretch()
        main_layout.addLayout(options_row)

        # Progress / Status
        self.status_label = QLabel("Inspecionando estado remoto e calculando diferenças...")
        self.status_label.setStyleSheet("font-size: 9.5pt; color: #BBB;")
        main_layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate during planning
        self.progress_bar.setFixedHeight(12)
        main_layout.addWidget(self.progress_bar)

        # Footer Buttons
        btn_row = QHBoxLayout()
        self.cancel_button = button("Cancelar", self._on_cancel)
        self.sync_button = button("🔄 Confirmar e Sincronizar", self._on_confirm_sync, primary=True)
        self.sync_button.setEnabled(False)

        btn_row.addWidget(self.cancel_button)
        btn_row.addStretch()
        btn_row.addWidget(self.sync_button)
        main_layout.addLayout(btn_row)

    def _start_planning(self) -> None:
        self._thread = QThread(self)
        self._worker = _PlanWorker(
            self.service, self.runtimes, self.scope, self.target_source_id, self.token
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_plan_finished)
        self._worker.failed.connect(self._on_plan_failed)
        self._worker.log_message.connect(self._on_log)
        self._thread.start()

    def _on_log(self, message: str) -> None:
        self.status_label.setText(message)

    def _on_plan_finished(self, plan: SyncPlan) -> None:
        self._cleanup_thread()
        self.plan = plan
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)

        self.val_new.setText(str(plan.new_count))
        self.val_upd.setText(str(plan.updated_count))
        self.val_rem.setText(str(plan.removed_count))
        self.val_unc.setText(str(plan.unchanged_count))

        # Populate table
        self.table.setRowCount(len(plan.items))
        for row, item in enumerate(plan.items):
            status_text = {
                SyncItemAction.NEW: "+ Novo",
                SyncItemAction.UPDATED: "~ Alterado",
                SyncItemAction.REMOVED: "- Removido",
                SyncItemAction.UNCHANGED: "= Inalterado",
                SyncItemAction.FAILED: "✕ Erro",
            }.get(item.action, item.action.value)

            status_item = QTableWidgetItem(status_text)
            color = {
                SyncItemAction.NEW: "#4CAF50",
                SyncItemAction.UPDATED: "#FFC107",
                SyncItemAction.REMOVED: "#F44336",
                SyncItemAction.UNCHANGED: "#9E9E9E",
                SyncItemAction.FAILED: "#E91E63",
            }.get(item.action, "#FFFFFF")
            status_item.setForeground(QColor(color))
            self.table.setItem(row, 0, status_item)
            self.table.setItem(row, 1, QTableWidgetItem(item.title))
            self.table.setItem(row, 2, QTableWidgetItem(item.container_id))
            self.table.setItem(row, 3, QTableWidgetItem(item.reason))

        if plan.has_changes:
            self.status_label.setText(
                f"Pronto para sincronizar: {plan.new_count} novos, {plan.updated_count} alterados, "
                f"{plan.removed_count} removidos."
            )
            self.sync_button.setEnabled(True)
        else:
            self.status_label.setText("Tudo atualizado! Nenhuma alteração pendente na fonte remota.")
            self.sync_button.setText("Sincronizado")
            self.sync_button.setEnabled(False)

    def _on_plan_failed(self, error: str) -> None:
        self._cleanup_thread()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Erro durante a verificação remota: {error}")
        self.sync_button.setEnabled(False)

    def _on_confirm_sync(self) -> None:
        if not self.plan:
            return
        self.sync_button.setEnabled(False)
        self.cancel_button.setText("Cancelar Execução")
        self.status_label.setText("Aplicando sincronização...")
        self.progress_bar.setRange(0, 0)

        options = SyncOptions(
            delete_removed_files=self.chk_delete_files.isChecked(),
            auto_consolidate=self.chk_consolidate.isChecked(),
        )

        self._thread = QThread(self)
        self._worker = _ApplyWorker(
            self.service, self.plan, self.runtimes, options, self.token
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_apply_progress)
        self._worker.finished.connect(self._on_apply_finished)
        self._worker.failed.connect(self._on_apply_failed)
        self._worker.log_message.connect(self._on_log)
        self._thread.start()

    def _on_apply_progress(self, done: int, total: int, item: str) -> None:
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(done)
        self.status_label.setText(f"[{done}/{total}] {item}")

    def _on_apply_finished(self, report: SyncReport) -> None:
        self._cleanup_thread()
        self.report = report
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.status_label.setText(
            f"Sincronização concluída com sucesso em {report.duration_seconds}s!"
        )
        self.cancel_button.setText("Concluir")
        self.sync_button.setText("Concluído")
        self.sync_button.setEnabled(False)

    def _on_apply_failed(self, error: str) -> None:
        self._cleanup_thread()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText(f"Erro na execução da sincronização: {error}")
        self.sync_button.setEnabled(True)

    def _on_cancel(self) -> None:
        if self._thread and self._thread.isRunning():
            self.token.cancel()
            self.status_label.setText("Cancelando operação...")
            self._thread.quit()
            self._thread.wait(2000)
        self.reject()

    def _cleanup_thread(self) -> None:
        if self._thread:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self._worker = None

    def closeEvent(self, event: Any) -> None:
        self._on_cancel()
        super().closeEvent(event)


__all__ = ["SyncPreviewDialog"]
