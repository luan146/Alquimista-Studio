from __future__ import annotations

import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from ..client import ConfluenceClient
from ..connectors.confluence import ConfluenceRestConnector
from ..errors import (
    AlquimistaError,
    ExtractionCancelledError,
)
from ..markdown import (
    KnowledgeDocumentRenderer,
    MarkdownTransformer,
    page_metadata,
    sha256_text,
)
from ..models import (
    EntryStatus,
    KnowledgeDocumentMetadata,
    ManifestDocument,
    ManifestEntry,
    ProjectConfig,
    SourceConfig,
    now_iso,
    stable_json_hash,
)
from ..reports import ContainerReport, DocumentResult, ExecutionReport, SourceReport
from ..runtime import CancellationToken, LogCallback, ProgressCallback
from ..storage import (
    FAILURES_NAME,
    MANIFEST_NAME,
    REPORT_NAME,
    FileTransaction,
    ManifestStore,
    confined_path,
)
from .helpers import sanitize_filename
from .runtime import SelectedDocumentRef, SourceRuntime


def _get_now_iso() -> str:
    import alquimista.services as s_mod

    fn = getattr(s_mod, "now_iso", now_iso)
    return fn()


class ExtractionService:
    def __init__(
        self,
        project: ProjectConfig,
        runtimes: list[SourceRuntime],
        project_dir: Path,
        *,
        partial_update_keys: set[str] | None = None,
        token: CancellationToken | None = None,
        log: LogCallback | None = None,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.project = project
        self.runtimes = runtimes
        self.project_dir = project_dir.resolve()
        self.partial_update_keys = partial_update_keys
        self.output_dir = (
            Path(project.output_dir).resolve()
            if Path(project.output_dir).is_absolute()
            else (self.project_dir / project.output_dir).resolve()
        )
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        self.progress = progress or (lambda _done, _total, _item: None)
        self.store = ManifestStore(
            self.output_dir / MANIFEST_NAME,
            project,
            log=self.log,
        )
        self._assigned_relative_paths: dict[str, str] = {}

    @staticmethod
    def _unique_legacy_aliases(entries: list[ManifestEntry]) -> dict[str, ManifestEntry]:
        aliases: dict[str, ManifestEntry] = {}
        ambiguous: set[str] = set()
        for entry in entries:
            if not entry.page_id:
                continue
            # Disambiguated 3-part alias (preferred when container_id is known).
            if entry.container_id:
                full_alias = f"{entry.source_id}:{entry.container_id}:{entry.page_id}"
                if full_alias in aliases and aliases[full_alias] is not entry:
                    ambiguous.add(full_alias)
                else:
                    aliases[full_alias] = entry
            # Legacy 2-part alias kept as a last-resort fallback for manifests
            # written before container_id existed. It is deliberately dropped
            # when ambiguous (same page_id under the same source but different
            # containers) so a stale entry never silently shadows the wrong doc.
            alias = f"{entry.source_id}:{entry.page_id}"
            if alias in aliases and aliases[alias] is not entry:
                ambiguous.add(alias)
            else:
                aliases[alias] = entry
        for alias in ambiguous:
            aliases.pop(alias, None)
        return aliases

    def _relative_page_path(
        self, source: SourceConfig, metadata: dict[str, Any]
    ) -> Path:
        base = Path(self.project.extraction.pages_subdir)
        source_part = sanitize_filename(source.source_slug)
        space_part = sanitize_filename(metadata["space_key"] or "sem_espaco")
        title_part = sanitize_filename(metadata.get("title") or "Sem título")
        filename = f"{title_part}.md"
        layout = self.project.extraction.path_layout
        if layout == "source":
            relative = base / source_part / filename
        elif layout == "space":
            relative = base / space_part / filename
        elif layout == "flat":
            relative = base / f"{source_part}_{filename}"
        else:
            relative = base / source_part / space_part / filename
        key = relative.as_posix().casefold()
        previous_page = self._assigned_relative_paths.get(key)
        if previous_page and previous_page != str(metadata["page_id"]):
            relative = relative.with_name(
                f"{title_part}_{sanitize_filename(str(metadata['page_id']), 32)}.md"
            )
        self._assigned_relative_paths[relative.as_posix().casefold()] = str(metadata["page_id"])
        return relative

    @staticmethod
    def _metadata_hash(metadata: dict[str, Any]) -> str:
        return stable_json_hash(
            {
                key: metadata.get(key)
                for key in (
                    "source_name",
                    "source_type",
                    "container_id",
                    "container_type",
                    "container_name",
                    "document_id",
                    "space_key",
                    "space_name",
                    "root_page_id",
                    "root_title",
                    "title",
                    "module",
                    "submodule",
                    "path",
                    "source_url",
                    "confluence_version",
                    "updated_at",
                    "etag",
                    "author",
                    "labels",
                )
            }
        )

    def _structured_report(
        self,
        *,
        started: float,
        collected_at: str,
        current: dict[str, ManifestEntry],
        discovered_keys: set[str],
        selected_keys: set[str],
        counters: Counter[str],
        failures: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        """Build the stable report model while preserving legacy counters."""
        report = ExecutionReport.start(
            self.project.project_name,
            str(self.output_dir),
            str(self.store.path),
        )
        report.executed_at = collected_at
        report.duration_seconds = round(time.monotonic() - started, 2)
        report.pages_found = len(discovered_keys)
        report.pages_selected = len(selected_keys)
        report.counters = dict(counters)
        report.failures = len(failures)
        entries_by_source: dict[str, list[ManifestEntry]] = defaultdict(list)
        for entry in current.values():
            entries_by_source[entry.source_id].append(entry)
        for runtime in self.runtimes:
            source_entries = entries_by_source.get(runtime.source.id, [])
            containers: list[ContainerReport] = []
            for container_id, documents in (runtime.documents_by_container or {}).items():
                selected_documents = [
                    item for item in source_entries
                    if item.container_id == container_id and item.selected
                ]
                c_obj = (runtime.containers or {}).get(container_id)
                c_name = str(
                    getattr(c_obj, "name", None)
                    or (c_obj.get("name") if isinstance(c_obj, dict) else None)
                    or container_id
                )
                containers.append(
                    ContainerReport(
                        source_id=runtime.source.id,
                        source_type=runtime.source.source_type,
                        container_id=container_id,
                        name=c_name,
                        documents_found=len(documents),
                        documents_selected=len(selected_documents),
                        documents=[
                            DocumentResult(
                                source_id=item.source_id,
                                source_type=item.source_type,
                                container_id=item.container_id,
                                document_id=item.document_id or item.page_id,
                                title=item.title,
                                status=item.status.value,
                                error=item.error_message,
                                markdown_path=item.markdown_path,
                            )
                            for item in selected_documents
                        ],
                    )
                )
            report.sources.append(
                SourceReport(
                    source_id=runtime.source.id,
                    source_type=runtime.source.source_type,
                    name=runtime.source.name,
                    containers=containers,
                )
            )
        return report.as_dict()

    def _adapt_legacy_runtimes(self) -> None:
        """Convert pre-connector runtimes to the common connector contract.

        Older callers supplied a cached Confluence tree directly. Keeping this
        adapter at the boundary preserves that API while ensuring the actual
        extraction algorithm is platform-neutral.
        """
        import alquimista.services as s_mod
        confluence_client_cls = getattr(s_mod, "ConfluenceClient", ConfluenceClient)

        for runtime in self.runtimes:
            if runtime.connector is not None:
                continue
            if runtime.source.source_type != "confluence_rest":
                raise AlquimistaError(
                    "Um runtime sem conector só é compatível com Confluence legado."
                )
            client = confluence_client_cls(
                runtime.source,
                self.project.extraction,
                secret=runtime.secret,
                token=self.token,
                log=self.log,
            )
            connector = ConfluenceRestConnector(
                runtime.source,
                self.project.extraction,
                secret=runtime.secret,
                token=self.token,
                log=self.log,
                client=client,
            )
            container_id = runtime.source.space_key or "__legacy__"
            metadata: dict[str, KnowledgeDocumentMetadata] = {}
            for raw in runtime.pages_by_id.values():
                item = connector._metadata(raw, container_id)
                metadata[item.id] = item
            runtime.connector = connector
            runtime.containers = {container_id: connector.get_source()}
            runtime.documents_by_container = {container_id: metadata}
            root_id = str(runtime.root.get("id", ""))
            runtime.selected_page_ids = [
                f"{runtime.source.id}:{container_id}:{document_id}"
                for document_id in runtime.selected_page_ids
                if document_id in metadata
                and (
                    runtime.source.root_mode == "space"
                    or runtime.source.include_root
                    or str(document_id) != root_id
                )
            ]

    @staticmethod
    def _summary_value(summary: Any, name: str, default: Any = None) -> Any:
        if isinstance(summary, dict):
            return summary.get(name, default)
        return getattr(summary, name, default)

    def _summary_metadata(
        self,
        runtime: SourceRuntime,
        summary: Any,
        *,
        container_id: str,
        document_id: str,
        document_key: str,
    ) -> dict[str, Any]:
        """Build a manifest-compatible fallback from discovery metadata."""
        updated_at = self._summary_value(summary, "updated_at")
        created_at = self._summary_value(summary, "created_at")

        def iso(value: Any) -> str | None:
            return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else None)

        source = runtime.source
        title = str(self._summary_value(summary, "title", document_id) or document_id)
        path = list(self._summary_value(summary, "path", []) or [])
        return {
            "source_id": source.id,
            "source_type": source.source_type,
            "container_id": container_id,
            "container_type": "space",
            "container_name": str(
                self._summary_value(summary, "container_name", "")
                or source.space_name
                or container_id
            ),
            "document_id": document_id,
            "parent_id": self._summary_value(summary, "parent_id"),
            "page_id": document_id,
            "document_key": document_key,
            "title": title,
            "source_url": str(self._summary_value(summary, "original_url", "") or ""),
            "source_name": source.name,
            "space_key": source.space_key or container_id,
            "space_name": source.space_name,
            "path": path,
            "ancestors": list(self._summary_value(summary, "ancestors", []) or []),
            "created_at": iso(created_at),
            "updated_at": iso(updated_at),
            "etag": self._summary_value(summary, "etag"),
            "document_type": str(self._summary_value(summary, "document_type", "document")),
            "metadata": dict(self._summary_value(summary, "metadata", {}) or {}),
        }

    @staticmethod
    def _canonical_entry_key(entry: ManifestEntry, project: ProjectConfig) -> str:
        del project
        container = str(entry.container_id or entry.space_key or "__legacy__")
        document = str(entry.document_id or entry.page_id)
        return f"{entry.source_id}:{container}:{document}"

    @staticmethod
    def _key_matches(
        key: str,
        candidates: set[str],
        *,
        source_id: str | None = None,
        container_id: str | None = None,
        document_id: str | None = None,
    ) -> bool:
        if key in candidates:
            return True
        if source_id is None or document_id is None:
            return False
        aliases = {f"{source_id}:{document_id}"}
        if container_id:
            aliases.add(f"{source_id}:{container_id}:{document_id}")
        return bool(aliases.intersection(candidates))

    def _effective_keys(self, runtime: SourceRuntime) -> list[str]:
        if self.partial_update_keys is None:
            return list(runtime.selected_page_ids)
        result: list[str] = []
        for key in runtime.selected_page_ids:
            parts = key.split(":", 2)
            if len(parts) != 3:
                if key in self.partial_update_keys:
                    result.append(key)
                continue
            if self._key_matches(
                key,
                self.partial_update_keys,
                source_id=parts[0],
                container_id=parts[1],
                document_id=parts[2],
            ):
                result.append(key)
        return result

    def _reconcile_manifest(
        self,
        *,
        previous: dict[str, ManifestEntry],
        current: dict[str, ManifestEntry],
        discovered_keys: set[str],
        selected_keys: set[str],
        complete_containers: set[tuple[str, str]],
        counters: Counter[str],
        transaction: FileTransaction,
        collected_at: str,
    ) -> None:
        """Apply one manifest lifecycle to both extraction algorithms."""
        configured = {source.id: source for source in self.project.sources}
        enabled = {source.id for source in self.project.sources if source.enabled}
        current_canonical = {
            self._canonical_entry_key(entry, self.project): key
            for key, entry in current.items()
        }
        for key, old in previous.items():
            canonical = self._canonical_entry_key(old, self.project)
            if canonical in current_canonical or key in current:
                continue
            if self.partial_update_keys is not None and not self._key_matches(
                canonical,
                self.partial_update_keys,
                source_id=old.source_id,
                container_id=old.container_id or old.space_key,
                document_id=old.document_id or old.page_id,
            ):
                current[key] = old.model_copy(deep=True)
                continue

            entry = old.model_copy(deep=True)
            if old.source_id not in configured:
                entry.status = EntryStatus.SOURCE_REMOVED
                counters[EntryStatus.SOURCE_REMOVED.value] += 1
            elif old.source_id not in enabled:
                entry.status = EntryStatus.SOURCE_DISABLED
                counters[EntryStatus.SOURCE_DISABLED.value] += 1
            elif canonical in discovered_keys and canonical not in selected_keys:
                entry.status = EntryStatus.UNSELECTED
                counters[EntryStatus.UNSELECTED.value] += 1
                page_path = (
                    confined_path(self.output_dir, entry.markdown_path)
                    if entry.markdown_path
                    else None
                )
                if self.project.extraction.cleanup_unselected_files and page_path:
                    transaction.stage_delete(page_path)
                if not self.project.extraction.keep_unselected_manifest_entries:
                    continue
            elif (
                self.project.extraction.detect_remote_removals
                and (old.source_id, str(old.container_id or old.space_key or "__legacy__"))
                in complete_containers
            ):
                entry.status = EntryStatus.REMOVED
                counters[EntryStatus.REMOVED.value] += 1
                page_path = (
                    confined_path(self.output_dir, entry.markdown_path)
                    if entry.markdown_path
                    else None
                )
                if self.project.extraction.delete_removed_files and page_path:
                    transaction.stage_delete(page_path)
            else:
                # A partial snapshot cannot prove that a remote document is gone.
                current[key] = old.model_copy(deep=True)
                continue
            entry.active = False
            entry.selected = False
            entry.checked_at = collected_at
            entry.packages = []
            current[key] = entry

    def _record_failure(
        self,
        *,
        runtime: SourceRuntime,
        summary: Any,
        key: str,
        container_id: str,
        document_id: str,
        old: ManifestEntry | None,
        exc: Exception,
        collected_at: str,
        current: dict[str, ManifestEntry],
        failures: dict[str, dict[str, str]],
        counters: Counter[str],
    ) -> None:
        self.log(
            f"Falha ao extrair página {document_id} ({self._summary_value(summary, 'title', document_id)}) "
            f"da fonte {runtime.source.name}: {exc}"
        )
        failures[key] = {
            "source": runtime.source.name,
            "page_id": document_id,
            "title": str(self._summary_value(summary, "title", document_id) or document_id),
            "error": str(exc),
        }
        if old and self.project.extraction.preserve_previous_on_error:
            entry = old.model_copy(deep=True)
            entry.status = EntryStatus.PRESERVED_AFTER_ERROR
            entry.error_message = str(exc)
            entry.checked_at = collected_at
        else:
            entry = ManifestEntry(
                **self._summary_metadata(
                    runtime,
                    summary,
                    container_id=container_id,
                    document_id=document_id,
                    document_key=key,
                ),
                checked_at=collected_at,
                status=EntryStatus.FAILED,
                error_message=str(exc),
                active=True,
                selected=True,
            )
        current[key] = entry
        counters[entry.status.value] += 1

    def _extract_generic_document(
        self,
        *,
        runtime: SourceRuntime,
        connector: Any,
        summary: Any,
        key: str,
        container_id: str,
        document_id: str,
        old: ManifestEntry | None,
        renderer: KnowledgeDocumentRenderer,
        transform_hash: str,
        collected_at: str,
        transaction: FileTransaction,
        counters: Counter[str],
    ) -> ManifestEntry:
        summary_updated = self._summary_value(summary, "updated_at")
        summary_updated_text = (
            summary_updated.isoformat()
            if hasattr(summary_updated, "isoformat")
            else summary_updated
        )
        summary_etag = self._summary_value(summary, "etag")
        summary_relative = old.markdown_path if old else ""
        if (
            old
            and summary_updated_text
            and (not summary_etag or old.etag == summary_etag)
            and old.updated_at == summary_updated_text
            and old.transform_config_hash == transform_hash
            and summary_relative
            and confined_path(self.output_dir, summary_relative).exists()
        ):
            entry = old.model_copy(deep=True)
            entry.status = EntryStatus.UNCHANGED
            entry.checked_at = collected_at
            entry.active = True
            entry.selected = True
            entry.error_message = ""
            counters[EntryStatus.UNCHANGED.value] += 1
            return entry
        document = None
        try:
            document = connector.get_document(document_id, container_id=container_id)
        except TypeError as exc:
            if "container_id" not in str(exc):
                raise
            document = connector.get_document(document_id)
        prepared = renderer.prepare(
            document,
            runtime.source,
            metadata_overrides={"container_id": container_id, "document_key": key},
        )
        normalized = prepared.metadata
        relative = self._relative_page_path(runtime.source, normalized)
        absolute = confined_path(self.output_dir, relative)
        metadata_hash = self._metadata_hash(normalized)
        if (
            old
            and summary_updated_text
            and (not summary_etag or old.etag == summary_etag)
            and old.updated_at == summary_updated_text
            and old.transform_config_hash == transform_hash
            and old.markdown_path
            and absolute.exists()
        ):
            entry = old.model_copy(deep=True)
            entry.status = EntryStatus.UNCHANGED
            entry.checked_at = collected_at
            entry.active = True
            entry.selected = True
            entry.error_message = ""
            counters[EntryStatus.UNCHANGED.value] += 1
            return entry
        if (
            old
            and self.project.extraction.use_version_shortcut
            and not self.project.extraction.force_reprocess
            and (not normalized.get("etag") or old.etag == normalized.get("etag"))
            and old.updated_at == normalized.get("updated_at")
            and old.metadata_hash == metadata_hash
            and old.transform_config_hash == transform_hash
            and absolute.exists()
        ):
            entry = old.model_copy(deep=True)
            entry.status = EntryStatus.UNCHANGED
            entry.checked_at = collected_at
            entry.active = True
            entry.selected = True
            entry.error_message = ""
            counters[EntryStatus.UNCHANGED.value] += 1
            return entry
        content = prepared.content
        if not content and not self.project.markdown.include_empty_pages:
            counters[EntryStatus.EMPTY_SKIPPED.value] += 1
            if old:
                entry = old.model_copy(deep=True)
                entry.status = EntryStatus.EMPTY_SKIPPED
                entry.checked_at = collected_at
                entry.error_message = ""
                entry.active = False
                entry.selected = True
                entry.packages = []
            else:
                entry = ManifestEntry(
                    **normalized,
                    checked_at=collected_at,
                    status=EntryStatus.EMPTY_SKIPPED,
                    active=False,
                    selected=True,
                )
            return entry
        content_hash = prepared.content_hash
        if old is None:
            status = EntryStatus.NEW
        elif not absolute.exists():
            status = EntryStatus.REPAIRED
        elif old.content_hash != content_hash:
            status = EntryStatus.UPDATED
        elif old.transform_config_hash != transform_hash:
            status = EntryStatus.FORMAT_UPDATED
        elif old.metadata_hash != metadata_hash:
            status = EntryStatus.METADATA_UPDATED
        else:
            status = EntryStatus.UNCHANGED
        output = renderer.render_prepared(prepared, collected_at, status.value)
        if status != EntryStatus.UNCHANGED or not absolute.exists():
            transaction.stage_text(absolute, output)
        if old and old.markdown_path and old.markdown_path != relative.as_posix():
            old_path = confined_path(self.output_dir, old.markdown_path)
            if old_path != absolute:
                transaction.stage_delete(old_path)
        entry = ManifestEntry(
            **normalized,
            collected_at=collected_at,
            checked_at=collected_at,
            first_collected_at=old.first_collected_at if old else collected_at,
            last_successful_at=collected_at,
            content_hash=content_hash,
            metadata_hash=metadata_hash,
            transform_config_hash=transform_hash,
            document_hash=sha256_text(output),
            markdown_path=relative.as_posix(),
            packages=old.packages if old else [],
            status=status,
            error_message="",
            active=True,
            selected=True,
        )
        counters[status.value] += 1
        return entry

    def _run_generic(self, transaction: FileTransaction) -> dict[str, Any]:
        """Run extraction through the platform-neutral connector contract."""
        started = time.monotonic()
        previous_document = self.store.load()
        previous = {entry.document_key: entry for entry in previous_document.entries}
        legacy_aliases = self._unique_legacy_aliases(previous_document.entries)
        current: dict[str, ManifestEntry] = {}
        failures: dict[str, dict[str, str]] = {}
        counters: Counter[str] = Counter()
        transform_hash = self.project.markdown.signature()
        collected_at = _get_now_iso()
        discovered_keys: set[str] = set()
        selected_keys: set[str] = set()
        total = sum(
            len(runtime.selected_page_ids)
            for runtime in self.runtimes
            if runtime.source.enabled
        )
        completed = 0
        renderer = KnowledgeDocumentRenderer(self.project.markdown)

        for runtime in self.runtimes:
            self.token.check()
            if not runtime.source.enabled or runtime.connector is None:
                continue
            connector = runtime.connector
            try:
                refs = list(runtime.selected_documents)
                if not refs:
                    refs = [
                        SelectedDocumentRef(
                            source_id=runtime.source.id,
                            container_id=parts[1],
                            document_id=parts[2],
                            metadata=(runtime.documents_by_container or {})
                            .get(parts[1], {})
                            .get(parts[2]),
                        )
                        for key in self._effective_keys(runtime)
                        if len(parts := key.split(":", 2)) == 3
                    ]
                if self.partial_update_keys is not None:
                    refs = [
                        item
                        for item in refs
                        if self._key_matches(
                            item.document_key,
                            self.partial_update_keys,
                            source_id=item.source_id,
                            container_id=item.container_id,
                            document_id=item.document_id,
                        )
                    ]
                for ref in refs:
                    self.token.check()
                    if ref.source_id != runtime.source.id:
                        continue
                    key = ref.document_key
                    container_id = ref.container_id
                    document_id = ref.document_id
                    summary = ref.metadata or (runtime.documents_by_container or {}).get(
                        container_id, {}
                    ).get(document_id)
                    if summary is None:
                        summary = KnowledgeDocumentMetadata(
                            id=document_id,
                            container_id=container_id,
                            title=document_id,
                            metadata={"synthetic": True},
                        )
                    discovered_keys.add(key)
                    selected_keys.add(key)
                    completed += 1
                    summary_title = str(
                        self._summary_value(summary, "title", document_id) or document_id
                    )
                    self.progress(completed, total, summary_title)
                    self.log(f"{runtime.source.name} [{completed}/{total}] {summary_title}")
                    # Prefer the disambiguated 3-part legacy alias when the
                    # container is known, then fall back to the 2-part alias
                    # for manifests written before container_id existed.
                    old = (
                        previous.get(key)
                        or legacy_aliases.get(f"{runtime.source.id}:{container_id}:{document_id}")
                        or legacy_aliases.get(f"{runtime.source.id}:{document_id}")
                    )
                    try:
                        current[key] = self._extract_generic_document(
                            runtime=runtime,
                            connector=connector,
                            summary=summary,
                            key=key,
                            container_id=container_id,
                            document_id=document_id,
                            old=old,
                            renderer=renderer,
                            transform_hash=transform_hash,
                            collected_at=collected_at,
                            transaction=transaction,
                            counters=counters,
                        )
                    except ExtractionCancelledError:
                        raise
                    except Exception as exc:
                        self._record_failure(
                            runtime=runtime,
                            summary=summary,
                            key=key,
                            container_id=container_id,
                            document_id=document_id,
                            old=old,
                            exc=exc,
                            collected_at=collected_at,
                            current=current,
                            failures=failures,
                            counters=counters,
                        )

            finally:
                connector.close()

        self._reconcile_manifest(
            previous=previous,
            current=current,
            discovered_keys=discovered_keys,
            selected_keys=selected_keys,
            complete_containers=set(),
            counters=counters,
            transaction=transaction,
            collected_at=collected_at,
        )

        manifest = ManifestDocument(
            project_id=self.project.project_id,
            project_name=self.project.project_name,
            generated_at=collected_at,
            entries=sorted(
                current.values(),
                key=lambda item: (
                    item.source_name.casefold(),
                    [part.casefold() for part in item.path],
                    item.title.casefold(),
                ),
            ),
        )
        if self.store.path.exists():
            transaction.stage_text(
                self.store.path.with_suffix(self.store.path.suffix + ".bak"),
                self.store.path.read_text(encoding="utf-8"),
            )
        transaction.stage_json(self.store.path, manifest.model_dump(mode="json"))
        transaction.stage_json(self.output_dir / FAILURES_NAME, failures)
        report = self._structured_report(
            started=started,
            collected_at=collected_at,
            current=current,
            discovered_keys=discovered_keys,
            selected_keys=selected_keys,
            counters=counters,
            failures=failures,
        )
        transaction.stage_json(self.output_dir / REPORT_NAME, report)
        transaction.commit()
        try:
            self.store.index.rebuild(manifest)
        except Exception as exc:
            self.log(f"Índice SQLite não atualizado; o manifesto JSON permanece válido: {exc}")
        self.log("Extração concluída.")
        return report

    @staticmethod
    def _summary_metadata_hash(metadata: dict[str, Any], old: ManifestEntry) -> str:
        completed = dict(metadata)
        if not completed.get("author"):
            completed["author"] = old.author
        if not completed.get("labels"):
            completed["labels"] = old.labels
        return ExtractionService._metadata_hash(completed)

    def run(self) -> dict[str, Any]:
        self.log(
            f"[Extração] Iniciando: saída={self.output_dir}; "
            f"manifesto={self.store.path}; runtimes={len(self.runtimes)}"
        )
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with FileTransaction(self.output_dir) as transaction:
            return self._run(transaction)

    def _run(self, transaction: FileTransaction) -> dict[str, Any]:
        if any(runtime.connector is None for runtime in self.runtimes):
            if any(runtime.connector is not None for runtime in self.runtimes):
                raise AlquimistaError(
                    "Não é possível misturar runtimes legados e conectores na mesma execução."
                )
            return self._run_legacy(transaction)
        return self._run_generic(transaction)

    def _run_legacy(self, transaction: FileTransaction) -> dict[str, Any]:
        """Compatibility-only Confluence path for callers from schema v2/v3."""
        started = time.monotonic()
        self._assigned_relative_paths = {}
        previous_document = self.store.load()
        previous = {entry.document_key: entry for entry in previous_document.entries}
        legacy_aliases = self._unique_legacy_aliases(previous_document.entries)
        current: dict[str, ManifestEntry] = {}
        failures: dict[str, dict[str, str]] = {}
        counters: Counter[str] = Counter()
        transform_hash = self.project.markdown.signature()
        collected_at = _get_now_iso()
        discovered_keys: set[str] = set()
        selected_keys: set[str] = set()
        complete_containers: set[tuple[str, str]] = set()
        total = sum(
            len(runtime.selected_page_ids)
            for runtime in self.runtimes
            if runtime.source.enabled
        )
        import alquimista.services as s_mod
        confluence_client_cls = getattr(s_mod, "ConfluenceClient", ConfluenceClient)
        completed = 0

        for runtime in self.runtimes:
            self.token.check()
            source = runtime.source
            if not source.enabled:
                continue
            with confluence_client_cls(
                source,
                self.project.extraction,
                secret=runtime.secret,
                token=self.token,
                log=self.log,
            ) as client:
                transformer = MarkdownTransformer(
                    client, source, runtime.root, self.project.markdown
                )
                root_id = str(runtime.root["id"])
                legacy_container = str(source.space_key or "__legacy__")
                discovered_keys.update(
                    f"{source.id}:{legacy_container}:{page_id}"
                    for page_id in runtime.pages_by_id
                )
                complete_containers.add((source.id, legacy_container))
                selected_ids = [
                    page_id
                    for page_id in runtime.selected_page_ids
                    if page_id in runtime.pages_by_id
                    and (
                        source.root_mode == "space"
                        or source.include_root
                        or page_id != root_id
                    )
                    and (
                        self.partial_update_keys is None
                        or self._key_matches(
                            f"{source.id}:{legacy_container}:{page_id}",
                            self.partial_update_keys,
                            source_id=source.id,
                            container_id=legacy_container,
                            document_id=page_id,
                        )
                    )
                ]
                selected_keys.update(
                    f"{source.id}:{legacy_container}:{page_id}"
                    for page_id in selected_ids
                )

                for page_id in selected_ids:
                    self.token.check()
                    completed += 1
                    summary = runtime.pages_by_id[page_id]
                    summary_meta = page_metadata(summary, source, runtime.root)
                    key = summary_meta["document_key"]
                    legacy_container = str(
                        summary_meta.get("space_key") or source.space_key or "__legacy__"
                    )
                    old = (
                        previous.get(key)
                        or (
                            legacy_aliases.get(f"{source.id}:{legacy_container}:{page_id}")
                            if legacy_container
                            else None
                        )
                        or legacy_aliases.get(f"{source.id}:{page_id}")
                    )
                    relative = self._relative_page_path(source, summary_meta)
                    absolute = confined_path(self.output_dir, relative)
                    self.progress(completed, total, summary_meta["title"])
                    self.log(
                        f"{source.name} [{completed}/{total}] {summary_meta['title']}"
                    )

                    shortcut_hash = (
                        self._summary_metadata_hash(summary_meta, old)
                        if old
                        else self._metadata_hash(summary_meta)
                    )
                    if (
                        old
                        and self.project.extraction.use_version_shortcut
                        and not self.project.extraction.force_reprocess
                        and old.confluence_version == summary_meta["confluence_version"]
                        and old.metadata_hash == shortcut_hash
                        and old.transform_config_hash == transform_hash
                        and absolute.exists()
                    ):
                        entry = old.model_copy(deep=True)
                        entry.status = EntryStatus.UNCHANGED
                        entry.checked_at = collected_at
                        entry.active = True
                        entry.selected = True
                        entry.error_message = ""
                        current[key] = entry
                        counters[EntryStatus.UNCHANGED.value] += 1
                        continue

                    try:
                        page = client.fetch_page(
                            page_id,
                            include_body=True,
                            include_labels=self.project.markdown.include_labels,
                        )
                        metadata = page_metadata(page, source, runtime.root)
                        technical = transformer.technical_markdown(page)
                        if not technical and not self.project.markdown.include_empty_pages:
                            counters["empty_skipped"] += 1
                            self.log(f"Página vazia ignorada: {metadata['title']}")
                            if old:
                                entry = old.model_copy(deep=True)
                                entry.status = EntryStatus.EMPTY_SKIPPED
                                entry.checked_at = collected_at
                                entry.error_message = ""
                                entry.active = False
                                entry.selected = True
                                entry.packages = []
                            else:
                                entry = ManifestEntry(
                                    **metadata,
                                    checked_at=collected_at,
                                    status=EntryStatus.EMPTY_SKIPPED,
                                    active=False,
                                    selected=True,
                                )
                            current[key] = entry
                            continue
                        content_hash = sha256_text(
                            transformer.hash_input(metadata, technical)
                        )
                        metadata_hash = self._metadata_hash(metadata)
                        if old is None:
                            status = EntryStatus.NEW
                        elif not absolute.exists():
                            status = EntryStatus.REPAIRED
                        elif old.content_hash != content_hash:
                            status = EntryStatus.UPDATED
                        elif old.transform_config_hash != transform_hash:
                            status = EntryStatus.FORMAT_UPDATED
                        elif old.metadata_hash != metadata_hash:
                            status = EntryStatus.METADATA_UPDATED
                        else:
                            status = EntryStatus.UNCHANGED
                        document = transformer.full_document(
                            metadata,
                            technical,
                            content_hash,
                            collected_at,
                            status.value,
                        )
                        if status != EntryStatus.UNCHANGED or not absolute.exists():
                            transaction.stage_text(absolute, document)
                        if (
                            old
                            and old.markdown_path
                            and old.markdown_path != relative.as_posix()
                        ):
                            old_path = confined_path(self.output_dir, old.markdown_path)
                            if old_path != absolute:
                                transaction.stage_delete(old_path)
                        entry = ManifestEntry(
                            **metadata,
                            collected_at=collected_at,
                            checked_at=collected_at,
                            first_collected_at=old.first_collected_at
                            if old
                            else collected_at,
                            last_successful_at=collected_at,
                            content_hash=content_hash,
                            metadata_hash=metadata_hash,
                            transform_config_hash=transform_hash,
                            document_hash=sha256_text(document),
                            markdown_path=relative.as_posix(),
                            packages=old.packages if old else [],
                            status=status,
                            error_message="",
                            active=True,
                            selected=True,
                        )
                        current[key] = entry
                        counters[status.value] += 1
                    except ExtractionCancelledError:
                        raise
                    except Exception as exc:
                        self.log(
                            f"Falha ao extrair pagina {page_id} "
                            f"({summary_meta['title']}) da fonte {source.name}: {exc}"
                        )
                        failures[key] = {
                            "source": source.name,
                            "page_id": page_id,
                            "title": summary_meta["title"],
                            "error": str(exc),
                        }

                        if old and self.project.extraction.preserve_previous_on_error:
                            entry = old.model_copy(deep=True)
                            entry.status = EntryStatus.PRESERVED_AFTER_ERROR
                            entry.error_message = str(exc)
                            entry.checked_at = collected_at
                            current[key] = entry
                            counters[EntryStatus.PRESERVED_AFTER_ERROR.value] += 1
                        else:
                            current[key] = ManifestEntry(
                                **summary_meta,
                                checked_at=collected_at,
                                status=EntryStatus.FAILED,
                                error_message=str(exc),
                                active=True,
                                selected=True,
                            )
                            counters[EntryStatus.FAILED.value] += 1
                        self.log(f"Falha em {summary_meta['title']}: {exc}")
                    self.token.wait(self.project.extraction.request_delay_ms / 1000)

        self._reconcile_manifest(
            previous=previous,
            current=current,
            discovered_keys=discovered_keys,
            selected_keys=selected_keys,
            complete_containers=complete_containers,
            counters=counters,
            transaction=transaction,
            collected_at=collected_at,
        )

        manifest = ManifestDocument(
            project_id=self.project.project_id,
            project_name=self.project.project_name,
            generated_at=collected_at,
            entries=sorted(
                current.values(),
                key=lambda item: (
                    item.source_name.casefold(),
                    [part.casefold() for part in item.path],
                    item.title.casefold(),
                ),
            ),
        )
        manifest.generated_at = _get_now_iso()
        if self.store.path.exists():
            transaction.stage_text(
                self.store.path.with_suffix(self.store.path.suffix + ".bak"),
                self.store.path.read_text(encoding="utf-8"),
            )
        transaction.stage_json(self.store.path, manifest.model_dump(mode="json"))
        transaction.stage_json(self.output_dir / FAILURES_NAME, failures)
        report = self._structured_report(
            started=started,
            collected_at=collected_at,
            current=current,
            discovered_keys=discovered_keys,
            selected_keys=selected_keys,
            counters=counters,
            failures=failures,
        )
        transaction.stage_json(self.output_dir / REPORT_NAME, report)
        transaction.commit()
        try:
            self.store.index.rebuild(manifest)
        except Exception as exc:
            self.log(f"Índice SQLite não atualizado; o manifesto JSON permanece válido: {exc}")
        self.log("Extração concluída.")
        return report


__all__ = ["ExtractionService"]
