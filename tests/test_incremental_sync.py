from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from alquimista.errors import ExtractionCancelledError
from alquimista.models import (
    EntryStatus,
    KnowledgeContainer,
    KnowledgeDocument,
    KnowledgeDocumentMetadata,
    ProjectConfig,
    SourceConfig,
)
from alquimista.runtime import CancellationToken
from alquimista.services import (
    IncrementalSyncService,
    SelectedDocumentRef,
    SourceRuntime,
    SyncItemAction,
    SyncOptions,
    SyncScope,
)
from alquimista.storage import MANIFEST_NAME, ManifestStore


class MockConnector:
    def __init__(self, source: SourceConfig) -> None:
        self.source = source
        self.containers = [
            KnowledgeContainer(
                id="c1",
                key="c1",
                name="Contêiner 1",
                container_type="space",
                source_type=source.source_type,
            )
        ]
        self.docs_meta: dict[str, list[KnowledgeDocumentMetadata]] = {
            "c1": [
                KnowledgeDocumentMetadata(
                    id="doc1",
                    container_id="c1",
                    title="Doc 1",
                    updated_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
                    etag="v1",
                ),
                KnowledgeDocumentMetadata(
                    id="doc2",
                    container_id="c1",
                    title="Doc 2",
                    updated_at=datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc),
                    etag="v1",
                ),
            ]
        }
        self.doc_bodies: dict[str, str] = {
            "doc1": "<h1>Doc 1</h1><p>Conteúdo original 1</p>",
            "doc2": "<h1>Doc 2</h1><p>Conteúdo original 2</p>",
        }
        self.get_document_calls: list[str] = []
        self.fail_container: str | None = None

    def list_containers(self) -> list[KnowledgeContainer]:
        return list(self.containers)

    def list_documents(self, container_id: str) -> list[KnowledgeDocumentMetadata]:
        if self.fail_container == container_id:
            raise RuntimeError(f"Falha de rede/autenticação no container {container_id}")
        return list(self.docs_meta.get(container_id, []))

    def get_document(self, document_id: str, container_id: str = "") -> KnowledgeDocument:
        self.get_document_calls.append(document_id)
        meta = next(
            (m for m in self.docs_meta.get(container_id or "c1", []) if m.id == document_id),
            KnowledgeDocumentMetadata(id=document_id, container_id=container_id or "c1", title=document_id),
        )
        return KnowledgeDocument(
            id=document_id,
            source_type=self.source.source_type,
            container_id=container_id or "c1",
            title=meta.title,
            content=self.doc_bodies.get(document_id, "<p>Default</p>"),
            updated_at=meta.updated_at,
            etag=meta.etag,
            metadata=meta.metadata,
        )

    def close(self) -> None:
        pass


@pytest.fixture
def sync_env(tmp_path: Path):
    output_dir = tmp_path / "output"
    source = SourceConfig(
        id="src1",
        name="Knowledge Base",
        source_type="generic_docs",
        base_url="https://docs.example.com",
    )
    project = ProjectConfig(
        project_name="TestSync",
        output_dir=str(output_dir),
        sources=[source],
    )
    connector = MockConnector(source)
    runtime = SourceRuntime(
        source=source,
        root={},
        pages_by_id={},
        selected_page_ids=["src1:c1:doc1", "src1:c1:doc2"],
        connector=connector,
        containers={"c1": connector.containers[0]},
        documents_by_container={"c1": {m.id: m for m in connector.docs_meta["c1"]}},
        selected_documents=[
            SelectedDocumentRef(source_id="src1", container_id="c1", document_id="doc1", metadata=connector.docs_meta["c1"][0]),
            SelectedDocumentRef(source_id="src1", container_id="c1", document_id="doc2", metadata=connector.docs_meta["c1"][1]),
        ],
    )
    service = IncrementalSyncService(project, tmp_path)
    return {
        "project": project,
        "source": source,
        "connector": connector,
        "runtime": runtime,
        "service": service,
        "output_dir": output_dir,
        "tmp_path": tmp_path,
    }


def test_initial_sync_all_new(sync_env):
    service: IncrementalSyncService = sync_env["service"]
    runtime: SourceRuntime = sync_env["runtime"]
    connector: MockConnector = sync_env["connector"]

    # 1. Plan sync: When manifest is empty, all remote docs are detected as NEW
    plan = service.plan_sync([runtime], scope=SyncScope.SOURCE, target_source_id="src1")
    assert plan.new_count == 2
    assert plan.updated_count == 0
    assert plan.removed_count == 0
    assert plan.unchanged_count == 0
    assert plan.has_changes is True
    assert "+ 2 novos" in plan.summary_text

    # 2. Apply sync
    report = service.apply_sync(plan, [runtime])
    assert report.summary["new"] == 2
    assert len(connector.get_document_calls) == 2

    # Verify manifest and files
    manifest_store = ManifestStore(sync_env["output_dir"] / MANIFEST_NAME, sync_env["project"])
    manifest = manifest_store.load()
    print("\nMANIFEST ENTRIES:", [(e.document_id, e.status, e.error_message) for e in manifest.entries])
    assert len(manifest.entries) == 2
    assert all(entry.status == EntryStatus.NEW for entry in manifest.entries)


def test_subsequent_sync_unchanged(sync_env):
    service: IncrementalSyncService = sync_env["service"]
    runtime: SourceRuntime = sync_env["runtime"]
    connector: MockConnector = sync_env["connector"]

    # Initial extraction
    plan = service.plan_sync([runtime], scope=SyncScope.SOURCE, target_source_id="src1")
    service.apply_sync(plan, [runtime])
    connector.get_document_calls.clear()

    # Second sync without any changes
    plan2 = service.plan_sync([runtime], scope=SyncScope.SOURCE, target_source_id="src1")
    assert plan2.new_count == 0
    assert plan2.updated_count == 0
    assert plan2.removed_count == 0
    assert plan2.unchanged_count == 2
    assert plan2.has_changes is False

    # Apply sync does not re-download unchanged bodies
    report2 = service.apply_sync(plan2, [runtime])
    assert len(connector.get_document_calls) == 0
    assert report2.summary["unchanged"] == 2


def test_sync_detects_updated_new_and_removed(sync_env):
    service: IncrementalSyncService = sync_env["service"]
    runtime: SourceRuntime = sync_env["runtime"]
    connector: MockConnector = sync_env["connector"]

    # Initial extraction
    plan1 = service.plan_sync([runtime], scope=SyncScope.SOURCE, target_source_id="src1")
    service.apply_sync(plan1, [runtime])
    connector.get_document_calls.clear()

    # Remote changes:
    # - doc1 is updated (new updated_at & etag)
    # - doc2 is removed from remote
    # - doc3 is added to remote
    connector.docs_meta["c1"] = [
        KnowledgeDocumentMetadata(
            id="doc1",
            container_id="c1",
            title="Doc 1 (Updated)",
            updated_at=datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc),
            etag="v2",
        ),
        KnowledgeDocumentMetadata(
            id="doc3",
            container_id="c1",
            title="Doc 3",
            updated_at=datetime(2026, 8, 2, 12, 0, 0, tzinfo=timezone.utc),
            etag="v1",
        ),
    ]
    connector.doc_bodies["doc1"] = "<h1>Doc 1</h1><p>Conteúdo atualizado</p>"
    connector.doc_bodies["doc3"] = "<h1>Doc 3</h1><p>Novo documento</p>"

    plan2 = service.plan_sync([runtime], scope=SyncScope.SOURCE, target_source_id="src1")
    assert plan2.new_count == 1  # doc3
    assert plan2.updated_count == 1  # doc1
    assert plan2.removed_count == 1  # doc2
    assert plan2.unchanged_count == 0

    report2 = service.apply_sync(plan2, [runtime], options=SyncOptions(delete_removed_files=True))
    assert report2.summary["new"] == 1
    assert report2.summary["updated"] == 1
    assert report2.summary["removed"] == 1

    # Verify only doc1 and doc3 were fetched
    assert set(connector.get_document_calls) == {"doc1", "doc3"}

    # Verify manifest reflects status
    manifest = ManifestStore(sync_env["output_dir"] / MANIFEST_NAME, sync_env["project"]).load()
    by_id = {e.document_id: e for e in manifest.entries}
    assert by_id["doc1"].status == EntryStatus.UPDATED
    assert by_id["doc1"].active is True
    assert by_id["doc3"].status == EntryStatus.NEW
    assert by_id["doc3"].active is True
    assert by_id["doc2"].status == EntryStatus.REMOVED
    assert by_id["doc2"].active is False


def test_sync_fail_safe_no_false_removals_on_error(sync_env):
    service: IncrementalSyncService = sync_env["service"]
    runtime: SourceRuntime = sync_env["runtime"]
    connector: MockConnector = sync_env["connector"]

    # Initial extraction
    plan1 = service.plan_sync([runtime], scope=SyncScope.SOURCE, target_source_id="src1")
    service.apply_sync(plan1, [runtime])

    # Simulate network/auth error during container discovery
    connector.fail_container = "c1"

    plan2 = service.plan_sync([runtime], scope=SyncScope.SOURCE, target_source_id="src1")
    # Fail-safe check: When container discovery fails, NO document should be classified as REMOVED!
    assert plan2.removed_count == 0
    assert len(plan2.failures) == 1
    assert "Falha de rede" in plan2.failures[0]["error"]

    # Applying sync must not delete anything
    service.apply_sync(plan2, [runtime])
    manifest = ManifestStore(sync_env["output_dir"] / MANIFEST_NAME, sync_env["project"]).load()
    assert all(e.active for e in manifest.entries)


def test_sync_cancellation(sync_env):
    service: IncrementalSyncService = sync_env["service"]
    runtime: SourceRuntime = sync_env["runtime"]

    token = CancellationToken()
    token.cancel()
    service.token = token

    with pytest.raises(ExtractionCancelledError):
        service.plan_sync([runtime], scope=SyncScope.SOURCE, target_source_id="src1")


def test_sync_scopes(sync_env):
    service: IncrementalSyncService = sync_env["service"]
    runtime: SourceRuntime = sync_env["runtime"]

    # Test Project Scope
    plan_proj = service.plan_sync([runtime], scope=SyncScope.PROJECT)
    assert plan_proj.scope == SyncScope.PROJECT
    assert "src1" in plan_proj.source_ids

    # Test Source Scope
    plan_src = service.plan_sync([runtime], scope=SyncScope.SOURCE, target_source_id="src1")
    assert plan_src.scope == SyncScope.SOURCE

    # Test Selection Scope
    plan_sel = service.plan_sync([runtime], scope=SyncScope.SELECTION)
    assert plan_sel.scope == SyncScope.SELECTION


def test_sync_attachments_detection(sync_env):
    service: IncrementalSyncService = sync_env["service"]
    runtime: SourceRuntime = sync_env["runtime"]
    connector: MockConnector = sync_env["connector"]

    # Initial extraction with attachment
    connector.docs_meta["c1"][0].metadata["attachments"] = [
        {"id": "att1", "filename": "plan.pdf", "size_bytes": 1024, "etag": "a1"}
    ]
    plan1 = service.plan_sync([runtime], scope=SyncScope.SOURCE, target_source_id="src1")
    service.apply_sync(plan1, [runtime])

    # Remote changes:
    # att1 size changes (updated)
    # att2 is added (new)
    connector.docs_meta["c1"][0].metadata["attachments"] = [
        {"id": "att1", "filename": "plan.pdf", "size_bytes": 2048, "etag": "a2"},
        {"id": "att2", "filename": "diagram.png", "size_bytes": 512, "etag": "d1"},
    ]

    plan2 = service.plan_sync([runtime], scope=SyncScope.SOURCE, target_source_id="src1")
    doc1_change = next(it for it in plan2.items if it.document_id == "doc1")
    assert doc1_change.action == SyncItemAction.UPDATED
    assert len(doc1_change.attachments) == 2
    att_actions = {a.id: a.action for a in doc1_change.attachments}
    assert att_actions["att1"] == SyncItemAction.UPDATED
    assert att_actions["att2"] == SyncItemAction.NEW


def test_sync_report_generation(sync_env):
    service: IncrementalSyncService = sync_env["service"]
    runtime: SourceRuntime = sync_env["runtime"]

    plan = service.plan_sync([runtime], scope=SyncScope.SOURCE, target_source_id="src1")
    report = service.apply_sync(plan, [runtime])
    assert report.scope == SyncScope.SOURCE
    assert report.summary["new"] == 2

    # Report file exists and is valid json
    report_path = sync_env["output_dir"] / "sync_report.json"
    assert report_path.exists()
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["scope"] == "source"
    assert data["summary"]["new"] == 2
    assert "duration_seconds" in data
