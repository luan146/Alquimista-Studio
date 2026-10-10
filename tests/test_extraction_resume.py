"""Extraction downloads in parallel, and an interrupted run keeps what it finished."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from alquimista.errors import AuthenticationError, ExtractionCancelledError
from alquimista.models import KnowledgeDocument, ProjectConfig, SourceConfig
from alquimista.runtime import CancellationToken
from alquimista.services import ExtractionService, SourceRuntime
from alquimista.services import extraction as extraction_module
from alquimista.storage import FAILURES_NAME, MANIFEST_NAME, ManifestStore

IDS = [f"doc-{n}" for n in range(1, 7)]


class _Connector:
    def __init__(self, crash_at: str | None = None):
        self.crash_at = crash_at

    def title(self, document_id: str) -> str:
        return document_id

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        if document_id == self.crash_at:
            raise KeyboardInterrupt  # stands in for the process dying mid-run
        return KnowledgeDocument(
            id=document_id,
            container_id="C",
            title=self.title(document_id),
            content=f"Texto {document_id}",
            source_type="generic",
        )

    def close(self) -> None:
        pass


def _service(tmp_path: Path, connector: _Connector, **kwargs: Any) -> ExtractionService:
    source = SourceConfig(id="s", name="Fonte", source_type="generic", base_url="https://docs.example.com")
    project = ProjectConfig(output_dir="base", sources=[source])
    runtime = SourceRuntime(
        source=source, root={}, pages_by_id={}, selected_page_ids=[f"s:C:{i}" for i in IDS], connector=connector
    )
    return ExtractionService(project, [runtime], tmp_path, **kwargs)


def _manifest_paths(tmp_path: Path) -> dict[str, str]:
    project = _service(tmp_path, _Connector()).project
    entries = ManifestStore(tmp_path / "base" / MANIFEST_NAME, project).load().entries
    return {entry.document_id: Path(entry.markdown_path).name for entry in entries}


def test_cancel_keeps_finished_documents_and_next_run_resumes(tmp_path: Path) -> None:
    token = CancellationToken()

    def cancel_at_third(done: int, _total: int, _title: str) -> None:
        if done == 3:
            token.cancel()  # the user presses "Cancelar" while doc-3 is processed

    with pytest.raises(ExtractionCancelledError):
        _service(tmp_path, _Connector(), token=token, progress=cancel_at_third).run()

    assert set(_manifest_paths(tmp_path)) == {"doc-1", "doc-2", "doc-3"}
    assert len(list((tmp_path / "base").rglob("*.md"))) == 3

    _service(tmp_path, _Connector()).run()

    assert set(_manifest_paths(tmp_path)) == set(IDS)
    assert len(list((tmp_path / "base").rglob("*.md"))) == 6


def test_crash_keeps_documents_up_to_the_last_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(extraction_module, "CHECKPOINT_FILES", 2)

    with pytest.raises(KeyboardInterrupt):
        _service(tmp_path, _Connector("doc-5")).run()

    assert set(_manifest_paths(tmp_path)) == {"doc-1", "doc-2", "doc-3", "doc-4"}
    assert not list((tmp_path / "base").glob(".alquimista-txn-*"))


class _SecondFinishesFirst(_Connector):
    """doc-1 only returns after doc-2 was downloaded: impossible one at a time."""

    def __init__(self) -> None:
        super().__init__()
        self.second_done = threading.Event()

    def title(self, document_id: str) -> str:
        return "Mesmo título" if document_id in {"doc-1", "doc-2"} else document_id

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        if document_id == "doc-1":
            assert self.second_done.wait(5), "downloads are not running in parallel"
        document = super().get_document(document_id, container_id)
        if document_id == "doc-2":
            self.second_done.set()
        return document


def test_downloads_run_in_parallel_but_file_names_follow_selection_order(tmp_path: Path) -> None:
    _service(tmp_path, _SecondFinishesFirst()).run()

    paths = _manifest_paths(tmp_path)
    assert set(paths) == set(IDS)
    # doc-2 finished first, yet doc-1 (first in the selection) keeps the plain name.
    assert paths["doc-1"] == "Mesmo_título.md"
    assert paths["doc-2"] != "Mesmo_título.md"


class _TokenExpiresAtThird(_Connector):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[str] = []

    def get_document(self, document_id: str, container_id: str | None = None) -> KnowledgeDocument:
        self.calls.append(document_id)
        if document_id >= "doc-3":
            raise AuthenticationError("A API recusou o token (HTTP 401).")
        return super().get_document(document_id, container_id)


def test_expired_token_stops_the_run_and_keeps_finished_documents(tmp_path: Path) -> None:
    connector = _TokenExpiresAtThird()
    service = _service(tmp_path, connector)
    service.project.extraction.parallel_downloads = 1

    with pytest.raises(AuthenticationError):
        service.run()

    # Stops at the first 401 instead of failing every remaining document one by one.
    assert "doc-6" not in connector.calls
    assert set(_manifest_paths(tmp_path)) == {"doc-1", "doc-2"}
    assert json.loads((tmp_path / "base" / FAILURES_NAME).read_text(encoding="utf-8")) == {}

    _service(tmp_path, _Connector()).run()  # after logging in again
    assert set(_manifest_paths(tmp_path)) == set(IDS)
