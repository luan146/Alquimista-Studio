from __future__ import annotations

import time
from typing import Any

from alquimista.services.sync import (
    SyncItemAction,
    SyncItemChange,
    SyncOptions,
    SyncPlan,
    SyncReport,
    SyncScope,
)
from alquimista.ui.dialogs.sync_dialog import SyncPreviewDialog


def _item(action: SyncItemAction, title: str) -> SyncItemChange:
    return SyncItemChange(
        document_key=f"s1:C:{title}",
        source_id="s1",
        source_type="confluence_rest",
        container_id="C",
        document_id=title,
        title=title,
        action=action,
        reason="motivo",
    )


def _plan(new: int = 1, updated: int = 1) -> SyncPlan:
    items = [_item(SyncItemAction.NEW, f"novo{i}") for i in range(new)]
    items += [_item(SyncItemAction.UPDATED, f"alt{i}") for i in range(updated)]
    items.append(_item(SyncItemAction.UNCHANGED, "igual"))
    return SyncPlan(
        scope=SyncScope.SOURCE,
        source_ids=["s1"],
        items=items,
        new_count=new,
        updated_count=updated,
        unchanged_count=1,
    )


def _report(failures: list[dict[str, str]] | None = None) -> SyncReport:
    return SyncReport(
        scope=SyncScope.SOURCE,
        duration_seconds=0.1,
        summary={},
        applied_items=[],
        failures=failures or [],
        consolidated=False,
    )


class FakeService:
    def __init__(self, plan: SyncPlan | None = None, report: SyncReport | None = None, *, block: bool = False):
        self.plan, self.report, self.block = plan, report, block
        self.options: SyncOptions | None = None
        self.log: Any = None
        self.progress: Any = None
        self.token: Any = None

    def plan_sync(self, _runtimes: Any, *, scope: SyncScope, target_source_id: str | None) -> SyncPlan:
        deadline = time.monotonic() + 5
        while self.block and time.monotonic() < deadline:
            self.token.check()  # raises once the dialog cancels
            time.sleep(0.01)
        if self.plan is None:
            raise RuntimeError("API fora do ar")
        return self.plan

    def apply_sync(self, _plan: SyncPlan, _runtimes: Any, *, options: SyncOptions) -> SyncReport:
        self.options = options
        self.progress(1, 1, "novo0")
        assert self.report is not None
        return self.report


def _dialog(qtbot: Any, service: FakeService) -> SyncPreviewDialog:
    dialog = SyncPreviewDialog(None, service, [], scope=SyncScope.SOURCE, target_source_id="s1")  # type: ignore[arg-type]
    qtbot.addWidget(dialog)
    return dialog


def test_preview_lists_changes_and_applies_with_chosen_options(qtbot: Any) -> None:
    service = FakeService(_plan(new=2, updated=1), _report())
    dialog = _dialog(qtbot, service)
    qtbot.waitUntil(lambda: dialog.plan is not None)

    assert (dialog.val_new.text(), dialog.val_upd.text(), dialog.val_unc.text()) == ("2", "1", "1")
    assert dialog.table.rowCount() == 4
    assert dialog.sync_button.isEnabled()

    dialog.chk_delete_files.setChecked(False)
    dialog._on_confirm_sync()
    qtbot.waitUntil(lambda: dialog.report is not None)

    assert service.options == SyncOptions(delete_removed_files=False, auto_consolidate=True)
    assert "sucesso" in dialog.status_label.text()


def test_failures_are_not_reported_as_success(qtbot: Any) -> None:
    dialog = _dialog(qtbot, FakeService(_plan(), _report([{"key": "s1:C:novo0", "error": "403"}])))
    qtbot.waitUntil(lambda: dialog.plan is not None)
    dialog._on_confirm_sync()
    qtbot.waitUntil(lambda: dialog.report is not None)

    assert "1 falha" in dialog.status_label.text()
    assert "sucesso" not in dialog.status_label.text()


def test_nothing_to_sync_disables_confirmation(qtbot: Any) -> None:
    dialog = _dialog(qtbot, FakeService(_plan(new=0, updated=0)))
    qtbot.waitUntil(lambda: dialog.plan is not None)

    assert not dialog.sync_button.isEnabled()
    assert dialog.sync_button.text() == "Sincronizado"


def test_planning_error_is_shown(qtbot: Any) -> None:
    dialog = _dialog(qtbot, FakeService(plan=None))
    qtbot.waitUntil(lambda: "API fora do ar" in dialog.status_label.text())

    assert not dialog.sync_button.isEnabled()


def test_cancel_waits_for_worker_instead_of_destroying_running_thread(qtbot: Any) -> None:
    dialog = _dialog(qtbot, FakeService(_plan(), block=True))
    dialog.show()
    qtbot.waitUntil(lambda: dialog._thread is not None and dialog._thread.isRunning())

    dialog.reject()
    assert dialog.isVisible()  # still open: the worker has not stopped yet
    assert not dialog.cancel_button.isEnabled()

    qtbot.waitUntil(lambda: not dialog.isVisible(), timeout=3000)
    assert dialog._thread is None


def test_sources_are_prepared_off_the_ui_thread(qtbot: Any) -> None:
    import threading

    threads: list[threading.Thread] = []

    def prepare(_token: Any) -> list[Any]:
        threads.append(threading.current_thread())
        return ["runtime"]

    service = FakeService(_plan(), _report())
    dialog = SyncPreviewDialog(None, service, prepare, scope=SyncScope.SOURCE)  # type: ignore[arg-type]
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: dialog.plan is not None)

    assert threads and threads[0] is not threading.main_thread()
    assert dialog.runtimes == ["runtime"]  # reused by the apply step


def test_connection_failure_while_preparing_is_shown_in_the_dialog(qtbot: Any) -> None:
    from alquimista.errors import AuthenticationError

    def prepare(_token: Any) -> list[Any]:
        raise AuthenticationError("Sessão expirada")

    dialog = SyncPreviewDialog(None, FakeService(_plan()), prepare, scope=SyncScope.SOURCE)  # type: ignore[arg-type]
    qtbot.addWidget(dialog)
    qtbot.waitUntil(lambda: "Sessão expirada" in dialog.status_label.text())

    assert not dialog.sync_button.isEnabled()
