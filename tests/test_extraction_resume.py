"""An interrupted extraction keeps what it already finished; the next run resumes."""
from __future__ import annotations

from pathlib import Path

import pytest

from alquimista.errors import ExtractionCancelledError
from alquimista.models import KnowledgeDocument, ProjectConfig, SourceConfig
from alquimista.runtime import CancellationToken
from alquimista.services import ExtractionService, SourceRuntime
from alquimista.services import extraction as extraction_module
from alquimista.storage import MANIFEST_NAME, ManifestStore

IDS = [f"doc-{n}" for n in range(1, 7)]


class _Connector:
    def __init__(self, fail_at: str | None = None, *, crash: bool = False, token: CancellationToken | None = None):
        self.fail_at, self.crash, self.token = fail_at, crash, token
        self.fetched: list[str] = []

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        if document_id == self.fail_at:
            if self.crash:
                raise KeyboardInterrupt  # stands in for the process dying mid-run
            assert self.token is not None
            self.token.cancel()
            self.token.check()
        self.fetched.append(document_id)
        return KnowledgeDocument(
            id=document_id, container_id="C", title=document_id, content=f"Texto {document_id}", source_type="generic"
        )

    def close(self) -> None:
        pass


def _service(tmp_path: Path, connector: _Connector, token: CancellationToken | None = None) -> ExtractionService:
    source = SourceConfig(id="s", name="Fonte", source_type="generic", base_url="https://docs.example.com")
    project = ProjectConfig(output_dir="base", sources=[source])
    runtime = SourceRuntime(
        source=source, root={}, pages_by_id={}, selected_page_ids=[f"s:C:{i}" for i in IDS], connector=connector
    )
    return ExtractionService(project, [runtime], tmp_path, token=token)


def _manifest_ids(tmp_path: Path) -> set[str]:
    service = _service(tmp_path, _Connector())
    return {entry.document_id for entry in ManifestStore(tmp_path / "base" / MANIFEST_NAME, service.project).load().entries}


def test_cancel_keeps_finished_documents_and_next_run_resumes(tmp_path: Path) -> None:
    token = CancellationToken()

    with pytest.raises(ExtractionCancelledError):
        _service(tmp_path, _Connector("doc-4", token=token), token).run()

    assert _manifest_ids(tmp_path) == {"doc-1", "doc-2", "doc-3"}
    assert len(list((tmp_path / "base").rglob("*.md"))) == 3

    resumed = _Connector()
    _service(tmp_path, resumed).run()

    assert _manifest_ids(tmp_path) == set(IDS)
    assert len(list((tmp_path / "base").rglob("*.md"))) == 6


def test_crash_keeps_documents_up_to_the_last_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extraction_module, "CHECKPOINT_FILES", 2)

    with pytest.raises(KeyboardInterrupt):
        _service(tmp_path, _Connector("doc-5", crash=True)).run()

    assert _manifest_ids(tmp_path) == {"doc-1", "doc-2", "doc-3", "doc-4"}
    assert not list((tmp_path / "base").glob(".alquimista-txn-*"))
