from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from ..errors import AlquimistaError
from ..models import (
    EntryStatus,
    KnowledgeDocumentMetadata,
    ManifestEntry,
    ProjectConfig,
    SourceConfig,
    now_iso,
)
from ..runtime import CancellationToken, LogCallback, ProgressCallback
from ..storage import (
    MANIFEST_NAME,
    FileTransaction,
    ManifestStore,
    confined_path,
)
from .consolidation import ConsolidationService
from .extraction import ExtractionService
from .helpers import sanitize_filename
from .runtime import SelectedDocumentRef, SourceRuntime


class SyncScope(StrEnum):
    SELECTION = "selection"
    SOURCE = "source"
    PROJECT = "project"


class SyncItemAction(StrEnum):
    NEW = "new"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    REMOVED = "removed"
    FAILED = "failed"
    PRESERVED_AFTER_ERROR = "preserved_after_error"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass(slots=True)
class AttachmentChange:
    id: str
    filename: str
    document_id: str
    action: SyncItemAction
    size_bytes: int = 0
    etag: str = ""
    relative_path: str = ""
    error: str = ""


@dataclass(slots=True)
class SyncItemChange:
    document_key: str
    source_id: str
    source_type: str
    container_id: str
    document_id: str
    title: str
    action: SyncItemAction
    reason: str = ""
    markdown_path: str = ""
    updated_at: str | None = None
    etag: str | None = None
    content_hash: str | None = None
    metadata_hash: str | None = None
    attachments: list[AttachmentChange] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    error_message: str = ""


@dataclass(slots=True)
class SyncPlan:
    scope: SyncScope
    source_ids: list[str]
    items: list[SyncItemChange]
    new_count: int = 0
    updated_count: int = 0
    removed_count: int = 0
    unchanged_count: int = 0
    failed_count: int = 0
    attachments_new_count: int = 0
    attachments_updated_count: int = 0
    attachments_removed_count: int = 0
    completed_containers: set[tuple[str, str]] = field(default_factory=set)
    failures: list[dict[str, str]] = field(default_factory=list)
    planned_at: str = field(default_factory=now_iso)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.new_count > 0
            or self.updated_count > 0
            or self.removed_count > 0
            or self.attachments_new_count > 0
            or self.attachments_updated_count > 0
            or self.attachments_removed_count > 0
        )

    @property
    def summary_text(self) -> str:
        return (
            f"+ {self.new_count} novos\n"
            f"~ {self.updated_count} alterados\n"
            f"- {self.removed_count} removidos\n"
            f"= {self.unchanged_count} sem alterações"
        )


@dataclass(slots=True)
class SyncOptions:
    delete_removed_files: bool = True
    auto_consolidate: bool = True


@dataclass(slots=True)
class SyncReport:
    scope: SyncScope
    duration_seconds: float
    summary: dict[str, int]
    applied_items: list[dict[str, Any]]
    failures: list[dict[str, str]]
    consolidated: bool
    generated_at: str = field(default_factory=now_iso)

    def as_dict(self) -> dict[str, Any]:
        return {
            "scope": self.scope.value,
            "duration_seconds": self.duration_seconds,
            "summary": self.summary,
            "applied_items": self.applied_items,
            "failures": self.failures,
            "consolidated": self.consolidated,
            "generated_at": self.generated_at,
        }


SYNC_REPORT_NAME = "sync_report.json"


class IncrementalSyncService:
    """Orchestration service for incremental sync across ALQuimista sources.

    Reuses existing ExtractionService, InventoryReconciliationService,
    ManifestStore, ManifestIndex, FileTransaction, and ConsolidationService.
    Guarantees safe remote-removal semantics, stable IDs, and atomic commits.
    """

    def __init__(
        self,
        project: ProjectConfig,
        project_dir: Path,
        *,
        store: ManifestStore | None = None,
        token: CancellationToken | None = None,
        log: LogCallback | None = None,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.project = project
        self.project_dir = project_dir.resolve()
        output_dir = Path(project.output_dir)
        self.output_dir = (
            output_dir if output_dir.is_absolute() else self.project_dir / output_dir
        ).resolve()
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        self.progress = progress or (lambda _done, _total, _item: None)
        self.store = store or ManifestStore(
            self.output_dir / MANIFEST_NAME, project, log=self.log
        )

    def _get_scoped_runtimes(
        self,
        runtimes: list[SourceRuntime],
        scope: SyncScope,
        target_source_id: str | None = None,
    ) -> list[SourceRuntime]:
        if scope == SyncScope.SOURCE and target_source_id:
            return [rt for rt in runtimes if rt.source.id == target_source_id and rt.source.enabled]
        if scope == SyncScope.PROJECT:
            return [rt for rt in runtimes if rt.source.enabled]
        return [rt for rt in runtimes if rt.source.enabled]

    def _matches_source_scope(self, source: SourceConfig, container_id: str, document_id: str) -> bool:
        """Enforces that discovery does not indiscriminately enumerate outside SourceConfig."""
        if source.space_key and str(source.space_key) != str(container_id):
            return False
        if source.root_mode == "id" and source.root_id and not source.include_root:
            if str(document_id) == str(source.root_id):
                return False
        return True

    def plan_sync(
        self,
        runtimes: list[SourceRuntime],
        *,
        scope: SyncScope = SyncScope.SOURCE,
        target_source_id: str | None = None,
    ) -> SyncPlan:
        """Discovers remote state and builds a SyncPlan without downloading document bodies."""
        scoped_runtimes = self._get_scoped_runtimes(runtimes, scope, target_source_id)
        if not scoped_runtimes:
            raise AlquimistaError("Nenhuma fonte ativa elegível para sincronização no escopo fornecido.")

        manifest = self.store.load()
        existing_by_key: dict[str, ManifestEntry] = {
            entry.document_key: entry for entry in manifest.entries
        }
        # Also build alias index for legacy keys
        existing_by_alias: dict[str, ManifestEntry] = {}
        for entry in manifest.entries:
            if entry.container_id and entry.document_id:
                existing_by_alias[f"{entry.source_id}:{entry.container_id}:{entry.document_id}"] = entry
            elif entry.page_id:
                existing_by_alias[f"{entry.source_id}:{entry.space_key or ''}:{entry.page_id}"] = entry

        discovered_keys: set[str] = set()
        completed_containers: set[tuple[str, str]] = set()
        failures: list[dict[str, str]] = []
        items: list[SyncItemChange] = []

        total_runtimes = len(scoped_runtimes)
        for r_idx, runtime in enumerate(scoped_runtimes, start=1):
            self.token.check()
            connector = runtime.connector
            if connector is None:
                continue

            source = runtime.source
            self.log(f"[{r_idx}/{total_runtimes}] Inspecionando estado remoto da fonte: {source.name}...")

            # 1. Discover target containers according to SourceConfig
            target_containers: list[Any] = []
            try:
                if source.space_key:
                    # Specific container configured
                    target_containers = [
                        type("ContainerMock", (), {"id": source.space_key, "name": source.space_name or source.space_key})()
                    ]
                else:
                    target_containers = list(connector.list_containers())
            except Exception as exc:
                failures.append({
                    "source_id": source.id,
                    "container_id": "",
                    "error": f"Falha ao listar contêineres: {exc}",
                })
                self.log(f"Aviso: Erro ao listar contêineres de {source.name}: {exc}")
                continue

            for container in target_containers:
                self.token.check()
                container_id = str(getattr(container, "id", container))
                if not self._matches_source_scope(source, container_id, ""):
                    continue

                container_success = True
                raw_docs: list[KnowledgeDocumentMetadata] = []
                try:
                    raw_docs = list(connector.list_documents(container_id))
                except Exception as exc:
                    container_success = False
                    failures.append({
                        "source_id": source.id,
                        "container_id": container_id,
                        "error": f"Falha ao listar documentos: {exc}",
                    })
                    self.log(f"Aviso: Erro ao listar documentos no contêiner {container_id}: {exc}")
                    continue

                if container_success:
                    completed_containers.add((source.id, container_id))

                # Process remote metadata items
                for meta in raw_docs:
                    self.token.check()
                    doc_id = str(meta.id)
                    if not self._matches_source_scope(source, container_id, doc_id):
                        continue

                    doc_key = f"{source.id}:{container_id}:{doc_id}"
                    discovered_keys.add(doc_key)

                    old_entry = existing_by_key.get(doc_key) or existing_by_alias.get(doc_key)
                    change = self._classify_document(
                        runtime=runtime,
                        container_id=container_id,
                        doc_id=doc_id,
                        doc_key=doc_key,
                        meta=meta,
                        old=old_entry,
                    )
                    items.append(change)

        # 2. Identify removals (Strictly bounded by completed_containers)
        # Never mark removed if container was not completely and successfully discovered
        scoped_source_ids = {rt.source.id for rt in scoped_runtimes}
        for entry in manifest.entries:
            if entry.source_id not in scoped_source_ids:
                continue

            container_id = str(entry.container_id or entry.space_key or "")
            doc_id = str(entry.document_id or entry.page_id or "")
            doc_key = entry.document_key or f"{entry.source_id}:{container_id}:{doc_id}"

            # Only check if container was successfully completed
            if (entry.source_id, container_id) in completed_containers:
                if doc_key not in discovered_keys and entry.active:
                    # Document was removed remotely
                    items.append(
                        SyncItemChange(
                            document_key=doc_key,
                            source_id=entry.source_id,
                            source_type=entry.source_type,
                            container_id=container_id,
                            document_id=doc_id,
                            title=entry.title,
                            action=SyncItemAction.REMOVED,
                            reason="Removido da fonte remota",
                            markdown_path=entry.markdown_path,
                            metadata=entry.model_dump(mode="json"),
                        )
                    )

        # Count summary
        new_cnt = sum(1 for it in items if it.action == SyncItemAction.NEW)
        upd_cnt = sum(1 for it in items if it.action == SyncItemAction.UPDATED)
        rem_cnt = sum(1 for it in items if it.action == SyncItemAction.REMOVED)
        unc_cnt = sum(1 for it in items if it.action == SyncItemAction.UNCHANGED)
        fl_cnt = sum(1 for it in items if it.action == SyncItemAction.FAILED)

        att_new = sum(len([a for a in it.attachments if a.action == SyncItemAction.NEW]) for it in items)
        att_upd = sum(len([a for a in it.attachments if a.action == SyncItemAction.UPDATED]) for it in items)
        att_rem = sum(len([a for a in it.attachments if a.action == SyncItemAction.REMOVED]) for it in items)

        plan = SyncPlan(
            scope=scope,
            source_ids=list(scoped_source_ids),
            items=items,
            new_count=new_cnt,
            updated_count=upd_cnt,
            removed_count=rem_cnt,
            unchanged_count=unc_cnt,
            failed_count=fl_cnt,
            attachments_new_count=att_new,
            attachments_updated_count=att_upd,
            attachments_removed_count=att_rem,
            completed_containers=completed_containers,
            failures=failures,
        )
        return plan

    def _classify_document(
        self,
        runtime: SourceRuntime,
        container_id: str,
        doc_id: str,
        doc_key: str,
        meta: KnowledgeDocumentMetadata,
        old: ManifestEntry | None,
    ) -> SyncItemChange:
        source = runtime.source
        title = meta.title or doc_id
        meta_dict = meta.metadata if isinstance(meta.metadata, dict) else {}
        updated_at = (
            meta.updated_at.isoformat()
            if meta.updated_at is not None and hasattr(meta.updated_at, "isoformat")
            else str(meta.updated_at)
            if meta.updated_at is not None
            else None
        )
        etag = meta.etag or meta_dict.get("etag")

        transform_hash = self.project.markdown.signature()

        # Determine expected relative path
        title_part = sanitize_filename(title or "Sem título")
        relative_path = f"{self.project.extraction.pages_subdir}/{sanitize_filename(source.source_slug)}/{title_part}.md"
        local_file = confined_path(self.output_dir, old.markdown_path if old and old.markdown_path else relative_path)

        if old is None or not old.active:
            return SyncItemChange(
                document_key=doc_key,
                source_id=source.id,
                source_type=source.source_type,
                container_id=container_id,
                document_id=doc_id,
                title=title,
                action=SyncItemAction.NEW,
                reason="Novo documento identificado na fonte remota",
                markdown_path=relative_path,
                updated_at=updated_at,
                etag=etag,
                metadata=meta_dict,
            )

        # Check local file existence
        if not local_file.exists():
            return SyncItemChange(
                document_key=doc_key,
                source_id=source.id,
                source_type=source.source_type,
                container_id=container_id,
                document_id=doc_id,
                title=title,
                action=SyncItemAction.UPDATED,
                reason="Arquivo local ausente ou corrompido (reparação necessária)",
                markdown_path=old.markdown_path or relative_path,
                updated_at=updated_at,
                etag=etag,
                metadata=meta_dict,
            )

        # Check timestamp shortcut
        if (
            updated_at
            and old.updated_at == updated_at
            and (not etag or old.etag == etag)
            and old.transform_config_hash == transform_hash
        ):
            # Check attachments if any
            att_changes = self._classify_attachments(old, meta)
            if any(a.action != SyncItemAction.UNCHANGED for a in att_changes):
                return SyncItemChange(
                    document_key=doc_key,
                    source_id=source.id,
                    source_type=source.source_type,
                    container_id=container_id,
                    document_id=doc_id,
                    title=title,
                    action=SyncItemAction.UPDATED,
                    reason="Anexos foram alterados ou adicionados",
                    markdown_path=old.markdown_path,
                    updated_at=updated_at,
                    etag=etag,
                    attachments=att_changes,
                    metadata=meta_dict,
                )
            return SyncItemChange(
                document_key=doc_key,
                source_id=source.id,
                source_type=source.source_type,
                container_id=container_id,
                document_id=doc_id,
                title=title,
                action=SyncItemAction.UNCHANGED,
                reason="Conteúdo e metadados inalterados",
                markdown_path=old.markdown_path,
                updated_at=updated_at,
                etag=etag,
                attachments=att_changes,
                metadata=meta_dict,
            )

        # If updated_at or etag changed or is unavailable, mark as UPDATED
        return SyncItemChange(
            document_key=doc_key,
            source_id=source.id,
            source_type=source.source_type,
            container_id=container_id,
            document_id=doc_id,
            title=title,
            action=SyncItemAction.UPDATED,
            reason="Timestamp ou versão alterada na fonte remota",
            markdown_path=old.markdown_path or relative_path,
            updated_at=updated_at,
            etag=etag,
            metadata=meta_dict,
        )

    def _classify_attachments(
        self, old: ManifestEntry, meta: KnowledgeDocumentMetadata
    ) -> list[AttachmentChange]:
        changes: list[AttachmentChange] = []
        old_att_list = (old.metadata or {}).get("attachments", []) if isinstance(old.metadata, dict) else []
        old_attachments = {
            str(att.get("id", "")): att for att in old_att_list if isinstance(att, dict)
        }
        new_attachments_meta = meta.metadata.get("attachments", [])
        if isinstance(new_attachments_meta, list):
            for att_item in new_attachments_meta:
                att_id = str(att_item.get("id", ""))
                filename = str(att_item.get("filename", att_id))
                size = int(att_item.get("size_bytes", 0))
                etag = str(att_item.get("etag", ""))
                if att_id not in old_attachments:
                    changes.append(
                        AttachmentChange(
                            id=att_id,
                            filename=filename,
                            document_id=str(meta.id),
                            action=SyncItemAction.NEW,
                            size_bytes=size,
                            etag=etag,
                        )
                    )
                else:
                    old_att = old_attachments.pop(att_id)
                    if (etag and old_att.get("etag") != etag) or (size and old_att.get("size_bytes") != size):
                        changes.append(
                            AttachmentChange(
                                id=att_id,
                                filename=filename,
                                document_id=str(meta.id),
                                action=SyncItemAction.UPDATED,
                                size_bytes=size,
                                etag=etag,
                            )
                        )
                    else:
                        changes.append(
                            AttachmentChange(
                                id=att_id,
                                filename=filename,
                                document_id=str(meta.id),
                                action=SyncItemAction.UNCHANGED,
                                size_bytes=size,
                                etag=etag,
                            )
                        )
            for removed_id, removed_att in old_attachments.items():
                changes.append(
                    AttachmentChange(
                        id=removed_id,
                        filename=str(removed_att.get("filename", removed_id)),
                        document_id=str(meta.id),
                        action=SyncItemAction.REMOVED,
                    )
                )
        return changes

    def apply_sync(
        self,
        plan: SyncPlan,
        runtimes: list[SourceRuntime],
        *,
        options: SyncOptions | None = None,
    ) -> SyncReport:
        """Executes the selective extraction according to SyncPlan."""
        start_time = time.monotonic()
        options = options or SyncOptions()
        scoped_runtimes = self._get_scoped_runtimes(runtimes, plan.scope)

        keys_to_extract = {
            item.document_key
            for item in plan.items
            if item.action in (SyncItemAction.NEW, SyncItemAction.UPDATED)
        }

        self.log(
            f"Iniciando sincronização incremental: {len(keys_to_extract)} itens a processar, "
            f"{plan.removed_count} remoções planejadas."
        )

        if keys_to_extract:
            effective_runtimes: list[SourceRuntime] = []
            for rt in scoped_runtimes:
                docs_by_container: dict[str, dict[str, KnowledgeDocumentMetadata]] = {
                    c_id: dict(docs) for c_id, docs in (rt.documents_by_container or {}).items()
                }
                rt_copy = SourceRuntime(
                    source=rt.source,
                    root=rt.root,
                    pages_by_id=rt.pages_by_id,
                    selected_page_ids=[],
                    secret=rt.secret,
                    connector=rt.connector,
                    containers=dict(rt.containers or {}),
                    documents_by_container=docs_by_container,
                    inventory_complete_containers=set(rt.inventory_complete_containers),
                    selected_documents=[],
                )
                for item in plan.items:
                    if item.source_id == rt.source.id and item.action in (
                        SyncItemAction.NEW,
                        SyncItemAction.UPDATED,
                    ):
                        rt_copy.selected_page_ids.append(item.document_key)
                        docs = docs_by_container.setdefault(item.container_id, {})
                        parsed_dt = None
                        if item.updated_at:
                            try:
                                parsed_dt = datetime.fromisoformat(item.updated_at)
                            except Exception:
                                parsed_dt = None
                        docs[item.document_id] = KnowledgeDocumentMetadata(
                            id=item.document_id,
                            container_id=item.container_id,
                            title=item.title,
                            updated_at=parsed_dt,
                            etag=item.etag,
                            metadata=item.metadata,
                        )
                        rt_copy.selected_documents.append(
                            SelectedDocumentRef(
                                source_id=item.source_id,
                                container_id=item.container_id,
                                document_id=item.document_id,
                                metadata=docs[item.document_id],
                            )
                        )
                effective_runtimes.append(rt_copy)

            extraction_service = ExtractionService(
                project=self.project,
                runtimes=effective_runtimes,
                project_dir=self.project_dir,
                partial_update_keys=keys_to_extract,
                token=self.token,
                log=self.log,
                progress=self.progress,
            )
            extraction_service.run()

        # Handle removals directly if there are any planned removals
        manifest = self.store.load()
        applied_removals = 0
        if plan.removed_count > 0:
            removed_keys = {
                item.document_key for item in plan.items if item.action == SyncItemAction.REMOVED
            }
            transaction = FileTransaction(self.output_dir)
            for entry in manifest.entries:
                if entry.document_key in removed_keys:
                    entry.active = False
                    entry.status = EntryStatus.REMOVED
                    entry.checked_at = now_iso()
                    applied_removals += 1
                    if options.delete_removed_files and entry.markdown_path:
                        local_path = confined_path(self.output_dir, entry.markdown_path)
                        if local_path.exists():
                            transaction.stage_delete(local_path)
            transaction.commit()
            self.store.save(manifest)

        # Consolidate if requested and configured
        consolidated = False
        if options.auto_consolidate and getattr(self.project, "consolidation", None):
            try:
                self.log("Atualizando consolidação de pacotes pós-sincronização...")
                ConsolidationService(
                    project=self.project,
                    project_dir=self.project_dir,
                    token=self.token,
                    log=self.log,
                    progress=self.progress,
                ).run()
                consolidated = True
            except Exception as exc:
                self.log(f"Aviso: Falha na auto-consolidação pós-sincronização: {exc}")

        duration = round(time.monotonic() - start_time, 2)
        summary = {
            "new": plan.new_count,
            "updated": plan.updated_count,
            "removed": applied_removals if plan.removed_count > 0 else 0,
            "unchanged": plan.unchanged_count,
            "failures": len(plan.failures),
        }

        report = SyncReport(
            scope=plan.scope,
            duration_seconds=duration,
            summary=summary,
            applied_items=[
                {
                    "document_key": it.document_key,
                    "title": it.title,
                    "action": it.action.value,
                    "reason": it.reason,
                }
                for it in plan.items
            ],
            failures=plan.failures,
            consolidated=consolidated,
        )

        # Save sync_report.json to output_dir
        report_file = self.output_dir / SYNC_REPORT_NAME
        try:
            report_file.parent.mkdir(parents=True, exist_ok=True)
            report_file.write_text(
                json.dumps(report.as_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            self.log(f"Aviso: Não foi possível salvar {SYNC_REPORT_NAME}: {exc}")

        self.log(f"Sincronização concluída com sucesso em {duration}s!")
        return report


__all__ = [
    "AttachmentChange",
    "IncrementalSyncService",
    "SYNC_REPORT_NAME",
    "SyncItemAction",
    "SyncItemChange",
    "SyncOptions",
    "SyncPlan",
    "SyncReport",
    "SyncScope",
]
