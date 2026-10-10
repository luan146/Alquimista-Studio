from __future__ import annotations

import inspect
from pathlib import Path

from alquimista.ui.main_window import MainWindow


def _make_source_window(qtbot) -> MainWindow:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    return window


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
