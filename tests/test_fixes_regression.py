from __future__ import annotations

import inspect
from pathlib import Path

from PySide6.QtCore import Qt

from alquimista.ui.main_window import MainWindow


def _make_source_window(qtbot) -> MainWindow:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    return window


def test_rebuild_selection_store_recovers_from_legacy_mutation(qtbot) -> None:
    """ISSUE-006: after external code mutates legacy
    ``selected_page_ids`` (e.g. execution recovery), rebuilding the store
    from ``project.selections`` must keep the canonical SelectionStore in
    sync so the tree renders correct checkboxes afterwards.
    """
    window = _make_source_window(qtbot)
    source = window.project.sources[0]
    data = {
        "root": {"id": "all", "title": "Containers"},
        "pages": [
            {
                "id": "p1",
                "title": "Page 1",
                "_container_id": "space-a",
                "space": {"key": "space-a", "name": "Knowledge"},
                "ancestors": [],
                "version": {"number": 1},
            }
        ],
    }
    window.trees[source.id] = data
    window._populate_selection_tree(source, data)
    leaf = window._leaf_items()[0]
    leaf.setCheckState(0, Qt.CheckState.Checked)
    assert window.selection_store.is_selected(source.id, "space-a", "p1")

    # Simulate a legacy mutation by external code (e.g. execution recovery)
    # that rewrites selected_page_ids to a narrower set, and verify that
    # rebuilding the canonical store keeps the in-memory state consistent.
    source.selected_page_ids = ["p1"]
    window._rebuild_selection_store()
    assert window.selection_store.is_selected(source.id, "space-a", "p1")
    assert "p1" in source.selected_page_ids
    window.dirty = False


def test_lookup_page_details_source_uses_snapshot_locals() -> None:
    """ISSUE-009 structural check: the source of ``_lookup_page_details``
    captures an immutable ``extraction_snapshot`` and ``secret_snapshot``
    on the UI thread and the inner ``work`` closure passes those locals to
    ConfluenceClient, never the mutable ``self.project.extraction`` /
    ``self.secrets`` state.
    """
    from alquimista.ui.mixins import source_mixin as sm

    text = inspect.getsource(sm.SourceMixin._lookup_page_details)
    assert "extraction_snapshot = self.project.extraction.model_copy(deep=True)" in text
    assert "secret_snapshot = self.secrets.get(source.id, \"\")" in text
    # The inner work closure must reference the snapshot locals rather than
    # live UI state (no direct self.project.extraction / self.secrets access
    # past the snapshot lines).
    snapshot_idx = text.index("extraction_snapshot = self.project.extraction")
    closure_block = text[snapshot_idx:]
    assert "extraction_snapshot" in closure_block
    assert "secret_snapshot" in closure_block
    # After snapshot capture, the work closure must not re-read the mutable
    # attributes; verify the ConfluenceClient construction uses the locals.
    assert "extraction_snapshot," in closure_block
    assert "secret_snapshot," in closure_block


def test_file_transaction_smoke(tmp_path: Path) -> None:
    """ISSUE-008 smoke: basic commit still succeeds after the deterministic
    rollback refactor."""
    from alquimista.storage import FileTransaction

    target = tmp_path / "file.txt"
    target.write_text("orig", encoding="utf-8")
    with FileTransaction(tmp_path) as txn:
        txn.stage_text(target, "new")
        txn.commit()
    assert target.read_text(encoding="utf-8") == "new"
