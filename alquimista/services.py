from __future__ import annotations

import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .client import ConfluenceClient
from .connectors.confluence import ConfluenceRestConnector
from .errors import AlquimistaError, ExtractionCancelledError, ManifestError, StorageError
from .markdown import (
    KnowledgeDocumentRenderer,
    MarkdownTransformer,
    knowledge_document_metadata,
    normalize_markdown,
    page_metadata,
    sha256_text,
)
from .models import (
    EntryStatus,
    KnowledgeDocumentMetadata,
    ManifestDocument,
    ManifestEntry,
    ProjectConfig,
    SourceConfig,
    now_iso,
    stable_json_hash,
)
from .reports import ContainerReport, DocumentResult, ExecutionReport, SourceReport
from .runtime import CancellationToken, LogCallback, ProgressCallback
from .storage import (
    FAILURES_NAME,
    MANIFEST_NAME,
    PACKAGE_INDEX_NAME,
    REPORT_NAME,
    FileTransaction,
    ManifestStore,
    confined_path,
)


@dataclass
class SourceRuntime:
    source: SourceConfig
    root: dict[str, Any]
    pages_by_id: dict[str, dict[str, Any]]
    # Historical field name retained for project compatibility. Values are
    # document keys for connector-backed runtimes.
    selected_page_ids: list[str]
    secret: str = ""
    connector: Any | None = None
    containers: dict[str, Any] | None = None
    documents_by_container: dict[str, dict[str, KnowledgeDocumentMetadata]] | None = None

    @property
    def is_generic(self) -> bool:
        return self.connector is not None

    @property
    def selected_document_keys(self) -> list[str]:
        if self.connector is None:
            return [f"{self.source.id}:{self.source.space_key}:{item}" for item in self.selected_page_ids]
        return list(self.selected_page_ids)


def sanitize_filename(value: str, maximum: int = 120) -> str:
    result = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "", value or "").strip()
    result = re.sub(r"\s+", "_", result).strip(" ._")
    reserved = {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{n}" for n in range(1, 10)),
        *(f"lpt{n}" for n in range(1, 10)),
    }
    if result.casefold() in reserved:
        result = f"_{result}"
    return (result or "sem_titulo")[:maximum]


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
                c_name = str(getattr(c_obj, "name", None) or (c_obj.get("name") if isinstance(c_obj, dict) else None) or container_id)
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
        for runtime in self.runtimes:
            if runtime.connector is not None:
                continue
            if runtime.source.source_type != "confluence_rest":
                raise AlquimistaError(
                    "Um runtime sem conector só é compatível com Confluence legado."
                )
            client = ConfluenceClient(
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
        collected_at = now_iso()
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
                for key in runtime.selected_page_ids:
                    self.token.check()
                    parts = key.split(":", 2)
                    if len(parts) != 3 or parts[0] != runtime.source.id:
                        continue
                    _source_id, container_id, document_id = parts
                    metadata_by_id = (runtime.documents_by_container or {}).get(container_id, {})
                    summary = metadata_by_id.get(document_id)
                    if summary is None:
                        continue
                    discovered_keys.add(key)
                    selected_keys.add(key)
                    completed += 1
                    self.progress(completed, total, summary.title)
                    self.log(f"{runtime.source.name} [{completed}/{total}] {summary.title}")
                    # Prefer the disambiguated 3-part legacy alias when the
                    # container is known, then fall back to the 2-part alias
                    # for manifests written before container_id existed.
                    old = (
                        previous.get(key)
                        or legacy_aliases.get(f"{runtime.source.id}:{container_id}:{document_id}")
                        or legacy_aliases.get(f"{runtime.source.id}:{document_id}")
                    )
                    summary_updated = summary.updated_at.isoformat() if summary.updated_at else None
                    summary_etag = summary.etag
                    if (
                        old
                        and summary_updated
                        and (not summary_etag or old.etag == summary_etag)
                        and old.updated_at == summary_updated
                        and old.transform_config_hash == transform_hash
                        and old.markdown_path
                        and confined_path(self.output_dir, old.markdown_path).exists()
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
                        document = connector.get_document(
                            document_id, container_id=container_id
                        )
                    except TypeError as exc:
                        # Keep compatibility with older third-party/test connectors
                        # that implemented the original one-argument contract.
                        if "container_id" not in str(exc):
                            raise
                        document = connector.get_document(document_id)
                    normalized = knowledge_document_metadata(document, runtime.source)
                    normalized["container_id"] = container_id
                    normalized["document_key"] = key
                    relative = self._relative_page_path(runtime.source, normalized)
                    absolute = confined_path(self.output_dir, relative)
                    metadata_hash = self._metadata_hash(normalized)
                    if (
                        old
                        and self.project.extraction.use_version_shortcut
                        and not self.project.extraction.force_reprocess
                        and (
                            not normalized.get("etag")
                            or old.etag == normalized.get("etag")
                        )
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
                        current[key] = entry
                        counters[EntryStatus.UNCHANGED.value] += 1
                        continue
                    try:
                        content = normalize_markdown(document.content)
                        if not content and not self.project.markdown.include_empty_pages:
                            counters[EntryStatus.EMPTY_SKIPPED.value] += 1
                            self.log(f"Página vazia ignorada: {normalized.get('title', document_id)}")
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
                            current[key] = entry
                            continue
                        content_hash = sha256_text(renderer.hash_input(normalized, content))
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
                        output = renderer.render(
                            normalized, content, content_hash, collected_at, status.value
                        )
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
                        current[key] = entry
                        counters[status.value] += 1
                    except Exception as exc:
                        self.log(
                            f"Falha ao extrair pagina {document_id} "
                            f"({summary.title}) da fonte {runtime.source.name}: {exc}"
                        )
                        failures[key] = {
                            "source": runtime.source.name,
                            "page_id": document_id,
                            "title": summary.title,
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
                                **normalized,
                                checked_at=collected_at,
                                status=EntryStatus.FAILED,
                                error_message=str(exc),
                                active=True,
                                selected=True,
                            )
                            counters[EntryStatus.FAILED.value] += 1
            finally:
                connector.close()

        for key, old in previous.items():
            if key in current:
                continue
            entry = old.model_copy(deep=True)
            if key not in selected_keys:
                entry.status = EntryStatus.UNSELECTED
                counters[EntryStatus.UNSELECTED.value] += 1
            entry.active = False
            entry.selected = False
            entry.checked_at = collected_at
            entry.packages = []
            current[key] = entry

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
        transaction.stage_json(self.output_dir / "falhas_alquimista.json", failures)
        report = self._structured_report(
            started=started,
            collected_at=collected_at,
            current=current,
            discovered_keys=discovered_keys,
            selected_keys=selected_keys,
            counters=counters,
            failures=failures,
        )
        transaction.stage_json(self.output_dir / "relatorio_alquimista.json", report)
        transaction.commit()
        try:
            self.store.index.rebuild(manifest)
        except Exception as exc:
            self.log(f"Índice SQLite não atualizado; o manifesto JSON permanece válido: {exc}")
        self.log("Extração concluída.")
        return report

    @staticmethod
    def _summary_metadata_hash(metadata: dict[str, Any], old: ManifestEntry) -> str:
        # Tree results may omit author and labels; preserve the known values for the shortcut.
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
        collected_at = now_iso()
        discovered_keys: set[str] = set()
        selected_keys: set[str] = set()
        total = sum(len(runtime.selected_page_ids) for runtime in self.runtimes if runtime.source.enabled)
        completed = 0
        for runtime in self.runtimes:
            self.token.check()
            source = runtime.source
            if not source.enabled:
                continue
            with ConfluenceClient(
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
                discovered_keys.update(
                    f"{source.id}:{page_id}" for page_id in runtime.pages_by_id
                )
                selected_ids = [
                    page_id
                    for page_id in runtime.selected_page_ids
                    if page_id in runtime.pages_by_id
                    and (
                        source.root_mode == "space"
                        or source.include_root
                        or page_id != root_id
                    )
                ]
                selected_keys.update(f"{source.id}:{page_id}" for page_id in selected_ids)

                for page_id in selected_ids:
                    self.token.check()
                    completed += 1
                    summary = runtime.pages_by_id[page_id]
                    summary_meta = page_metadata(summary, source, runtime.root)
                    key = summary_meta["document_key"]
                    # Prefer the disambiguated 3-part legacy alias (space_key
                    # acts as the container in the legacy flow), then fall back
                    # to the 2-part alias for older manifests.
                    legacy_container = str(summary_meta.get("space_key") or source.space_key or "")
                    old = (
                        previous.get(key)
                        or (legacy_aliases.get(f"{source.id}:{legacy_container}:{page_id}") if legacy_container else None)
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
                        if old and old.markdown_path and old.markdown_path != relative.as_posix():
                            old_path = confined_path(self.output_dir, old.markdown_path)
                            if old_path != absolute:
                                transaction.stage_delete(old_path)
                        entry = ManifestEntry(
                            **metadata,
                            collected_at=collected_at,
                            checked_at=collected_at,
                            first_collected_at=old.first_collected_at if old else collected_at,
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
                            f"({summary_meta["title"]}) da fonte {source.name}: {exc}"
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

        configured = {source.id: source for source in self.project.sources}
        runtime_ids = {runtime.source.id for runtime in self.runtimes}
        for key, old in previous.items():
            if key in current:
                continue
            if self.partial_update_keys is not None and key not in self.partial_update_keys:
                current[key] = old.model_copy(deep=True)
                continue
            entry = old.model_copy(deep=True)
            page_path = (
                confined_path(self.output_dir, entry.markdown_path)
                if entry.markdown_path
                else None
            )
            if entry.source_id not in configured:
                entry.status = EntryStatus.SOURCE_REMOVED
                counters[EntryStatus.SOURCE_REMOVED.value] += 1
            elif entry.source_id not in runtime_ids:
                entry.status = EntryStatus.SOURCE_DISABLED
                counters[EntryStatus.SOURCE_DISABLED.value] += 1
            elif key in discovered_keys and key not in selected_keys:
                entry.status = EntryStatus.UNSELECTED
                counters[EntryStatus.UNSELECTED.value] += 1
                if self.project.extraction.cleanup_unselected_files and page_path:
                    transaction.stage_delete(page_path)
                if not self.project.extraction.keep_unselected_manifest_entries:
                    continue
            elif self.project.extraction.detect_remote_removals:
                entry.status = EntryStatus.REMOVED
                counters[EntryStatus.REMOVED.value] += 1
                if self.project.extraction.delete_removed_files and page_path:
                    transaction.stage_delete(page_path)
            entry.active = False
            entry.selected = False
            entry.checked_at = collected_at
            entry.packages = []
            current[key] = entry

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
        manifest.generated_at = now_iso()
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


def demote_headings(markdown: str, levels: int) -> str:
    if levels <= 0:
        return markdown
    return re.sub(
        r"^(#{1,6})\s+(.+)$",
        lambda match: f"{'#' * min(6, len(match.group(1)) + levels)} {match.group(2)}",
        markdown,
        flags=re.MULTILINE,
    )


class ConsolidationService:
    def __init__(
        self,
        project: ProjectConfig,
        project_dir: Path,
        *,
        selected_keys: set[str] | None = None,
        token: CancellationToken | None = None,
        log: LogCallback | None = None,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.project = project
        self.project_dir = project_dir.resolve()
        self.base_dir = (
            Path(project.output_dir).resolve()
            if Path(project.output_dir).is_absolute()
            else (self.project_dir / project.output_dir).resolve()
        )
        self.output_dir = confined_path(
            self.base_dir, project.consolidation.output_subdir
        )
        self.selected_keys = selected_keys
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        self.progress = progress or (lambda _done, _total, _item: None)
        self.store = ManifestStore(
            self.base_dir / MANIFEST_NAME,
            project,
            log=self.log,
        )

    def _group_key(self, entry: ManifestEntry) -> str:
        options = self.project.consolidation
        if options.grouping == "module":
            # entry.path is [root, module, ..., page]. Exclude the root and page.
            hierarchy = list(entry.path[1:-1])
            if not hierarchy:
                hierarchy = [entry.module or "Sem módulo"]
            depth = max(1, min(options.module_depth, len(hierarchy)))
            return "__".join(hierarchy[:depth])
        mapping = {
            "single": "Base completa",
            "source": entry.source_name or "Sem fonte",
            "space": entry.space_key or "Sem espaço",
            "module": entry.module or "Sem módulo",
            "module_submodule": f"{entry.module}__{entry.submodule or 'Geral'}",
            "source_module": f"{entry.source_name}__{entry.module or 'Sem módulo'}",
            "source_module_submodule": (
                f"{entry.source_name}__{entry.module or 'Sem módulo'}__"
                f"{entry.submodule or 'Geral'}"
            ),
            "manual": options.manual_groups.get(
                entry.document_key, "Sem grupo manual"
            ),
        }
        return mapping[options.grouping]

    def _entries(self) -> tuple[ManifestDocument, list[ManifestEntry]]:
        self.token.check()
        self.log(
            f"[Consolidação] Base={self.base_dir}; saída={self.output_dir}; "
            f"manifesto={self.store.path}; selected_only={self.project.consolidation.selected_only}; "
            f"active_only={self.project.consolidation.active_only}"
        )
        manifest = self.store.load()
        if not manifest.entries:
            raise ManifestError(f"Manifesto vazio ou inexistente: {self.store.path}")
        self.log(f"[Consolidação] Manifesto carregado com {len(manifest.entries)} entradas.")
        entries = []
        for entry in manifest.entries:
            self.token.check()
            if self.project.consolidation.active_only and not entry.active:
                continue
            if self.project.consolidation.selected_only and not entry.selected:
                continue
            if self.selected_keys is not None and entry.document_key not in self.selected_keys:
                continue
            source = next(
                (item for item in self.project.sources if item.id == entry.source_id),
                None,
            )
            if source and entry.page_id in source.consolidation_excluded_page_ids:
                continue
            if entry.status == EntryStatus.FAILED:
                continue
            if entry.status == EntryStatus.EMPTY_SKIPPED:
                continue
            entries.append(entry)
        if not entries:
            self.log(
                "[Consolidação] Nenhuma entrada passou pelos filtros. "
                f"selected_keys={len(self.selected_keys or set())}"
            )
            raise AlquimistaError("Nenhuma página atende aos filtros da consolidação.")
        self.log(f"[Consolidação] {len(entries)} entradas elegíveis para consolidação.")
        return manifest, entries

    def _page_text(self, entry: ManifestEntry) -> str:
        self.token.check()
        path = confined_path(self.base_dir, entry.markdown_path)
        self.log(
            f"[Consolidação] Lendo documento {entry.document_key}: "
            f"relativo={entry.markdown_path!r}; absoluto={path}; existe={path.is_file()}"
        )
        if not path.is_file():
            raise ManifestError(
                f"O manifesto {self.store.path} aponta para um arquivo inexistente: "
                f"{entry.markdown_path} "
                f"(resolvido para {path})"
            )
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ManifestError(
                f"Não foi possível ler o arquivo do manifesto: {entry.markdown_path} "
                f"(resolvido para {path})"
            ) from exc
        self.token.check()
        if not text:
            raise ManifestError(
                f"O manifesto {self.store.path} aponta para um arquivo vazio: "
                f"{entry.markdown_path}"
            )
        return text

    @staticmethod
    def _unique_package_filename(
        proposed: str,
        identity: str,
        assigned: set[str],
    ) -> str:
        candidate = proposed
        key = candidate.casefold()
        if key not in assigned:
            assigned.add(key)
            return candidate
        stem = Path(proposed).stem
        suffix = Path(proposed).suffix
        digest = stable_json_hash({"package": identity})[:8]
        candidate = f"{stem}_{digest}{suffix}"
        counter = 2
        while candidate.casefold() in assigned:
            candidate = f"{stem}_{digest}_{counter}{suffix}"
            counter += 1
        assigned.add(candidate.casefold())
        return candidate

    def _sort(self, entries: list[ManifestEntry]) -> list[ManifestEntry]:
        mode = self.project.consolidation.sort_mode
        if mode == "title":
            return sorted(entries, key=lambda item: item.title.casefold())
        if mode == "updated":
            return sorted(entries, key=lambda item: item.updated_at or "", reverse=True)
        if mode == "id":
            return sorted(entries, key=lambda item: item.page_id)
        return sorted(entries, key=lambda item: ([p.casefold() for p in item.path], item.title.casefold()))

    def _estimate_overhead(self, entries: list[ManifestEntry]) -> int:
        options = self.project.consolidation
        overhead = 300 if options.include_package_header else 0
        if options.include_package_index:
            overhead += sum(len(entry.title) + len(entry.source_url) + 20 for entry in entries)
        if options.include_page_separator:
            overhead += max(0, len(entries) - 1) * 8
        return overhead

    def preview(self) -> list[dict[str, Any]]:
        self.token.check()
        _manifest, entries = self._entries()
        groups: dict[str, list[ManifestEntry]] = defaultdict(list)
        for entry in entries:
            self.token.check()
            groups[self._group_key(entry)].append(entry)
        result: list[dict[str, Any]] = []
        for group, group_entries in sorted(groups.items()):
            self.token.check()
            current: list[ManifestEntry] = []
            chars = 0
            chunks: list[list[ManifestEntry]] = []
            for entry in self._sort(group_entries):
                self.token.check()
                size = len(self._page_text(entry))
                projected = chars + size + self._estimate_overhead([*current, entry])
                if current and (
                    len(current) >= self.project.consolidation.max_pages
                    or projected > self.project.consolidation.max_chars
                ):
                    chunks.append(current)
                    current = []
                    chars = 0
                current.append(entry)
                chars += size
            if current:
                chunks.append(current)
            for part, chunk in enumerate(chunks, 1):
                self.token.check()
                size = sum(len(self._page_text(entry)) for entry in chunk) + self._estimate_overhead(chunk)
                result.append(
                    {
                        "group": group,
                        "part": part,
                        "parts": len(chunks),
                        "pages": len(chunk),
                        "characters": size,
                        "oversized": len(chunk) == 1
                        and size > self.project.consolidation.max_chars,
                        "document_keys": [entry.document_key for entry in chunk],
                    }
                )
        return result

    def run(self) -> dict[str, Any]:
        self.log(
            f"[Consolidação] Iniciando: base={self.base_dir}; "
            f"saída={self.output_dir}; manifesto={self.store.path}"
        )
        self.base_dir.mkdir(parents=True, exist_ok=True)
        with FileTransaction(self.base_dir) as transaction:
            return self._run(transaction)

    def _run(self, transaction: FileTransaction) -> dict[str, Any]:
        started = time.monotonic()
        self.token.check()
        manifest, entries = self._entries()
        self.token.check()
        preview = self.preview()
        self.token.check()
        old_index_path = self.output_dir / PACKAGE_INDEX_NAME
        if self.project.consolidation.clean_output and old_index_path.exists():
            try:
                old_index = json.loads(old_index_path.read_text(encoding="utf-8"))
                for package in old_index.get("packages", []):
                    filename = package.get("filename", "")
                    if filename:
                        transaction.stage_delete(confined_path(self.output_dir, filename))
            except (OSError, json.JSONDecodeError, StorageError):
                self.log("Não foi possível limpar todos os pacotes registrados anteriormente.")

        by_key = {entry.document_key: entry for entry in entries}
        package_records: list[dict[str, Any]] = []
        packages_by_document: dict[str, list[str]] = defaultdict(list)
        assigned_filenames: set[str] = set()
        prefix = (
            sanitize_filename(self.project.consolidation.filename_prefix, 30) + "_"
            if self.project.consolidation.filename_prefix.strip()
            else ""
        )
        for index, item in enumerate(preview, 1):
            self.token.check()
            group = item["group"]
            suffix = f"_parte_{item['part']:02d}" if item["parts"] > 1 else ""
            proposed = f"{prefix}{sanitize_filename(group.replace('__', '_'))}{suffix}.md"
            filename = self._unique_package_filename(
                proposed,
                f"{group}:{item['part']}:{item['parts']}",
                assigned_filenames,
            )
            selected = [by_key[key] for key in item["document_keys"]]
            valid = []
            for entry in selected:
                self.token.check()
                valid.append((entry, self._page_text(entry)))
            valid = [(entry, text) for entry, text in valid if text]
            lines: list[str] = []
            options = self.project.consolidation
            if options.include_package_header:
                lines.extend(
                    [
                        f"# ALQuimista — {group.replace('__', ' — ')}",
                        "",
                        f"> Pacote consolidado com {len(valid)} documentos.",
                        "",
                    ]
                )
            if options.include_package_index:
                lines.extend(["## Índice", ""])
                for entry, _text in valid:
                    identifier = f"`DOC-{entry.page_id}` — " if options.include_ids_in_index else ""
                    title = (
                        f"[{entry.title}]({entry.source_url})"
                        if options.include_source_links_in_index and entry.source_url
                        else entry.title
                    )
                    lines.append(f"- {identifier}{title}")
                lines.append("")
            for page_index, (_entry, text) in enumerate(valid):
                if options.include_hierarchy_headings:
                    hierarchy = list(_entry.path[:-1])
                    for level, title in enumerate(hierarchy, 2):
                        lines.extend([f"{'#' * min(6, level)} {title}", ""])
                lines.append(demote_headings(text, options.demote_page_headings))
                if options.include_page_separator and page_index < len(valid) - 1:
                    lines.extend(["", "---", ""])
            transaction.stage_text(
                self.output_dir / filename,
                normalize_markdown("\n".join(lines)) + "\n",
            )
            for entry, _text in valid:
                packages_by_document[entry.document_key].append(filename)
            record = {
                **item,
                "pages": len(valid),
                "document_keys": [entry.document_key for entry, _text in valid],
                "filename": filename,
            }
            package_records.append(record)
            self.progress(index, len(preview), filename)
            self.log(f"Pacote criado: {filename} ({len(valid)} documentos).")

        for entry in manifest.entries:
            entry.packages = packages_by_document.get(entry.document_key, [])
        manifest.generated_at = now_iso()
        if self.store.path.exists():
            transaction.stage_text(
                self.store.path.with_suffix(self.store.path.suffix + ".bak"),
                self.store.path.read_text(encoding="utf-8"),
            )
        transaction.stage_json(self.store.path, manifest.model_dump(mode="json"))
        index_data = {
            "schema_version": 3,
            "project": self.project.project_name,
            "generated_at": now_iso(),
            "grouping": self.project.consolidation.grouping,
            "packages": package_records,
        }
        if self.project.consolidation.include_package_manifest:
            transaction.stage_json(old_index_path, index_data)
        else:
            transaction.stage_delete(old_index_path)
        transaction.commit()
        try:
            self.store.index.rebuild(manifest)
        except Exception as exc:
            self.log(f"Índice SQLite não atualizado; o manifesto JSON permanece válido: {exc}")
        result = {
            "output_dir": str(self.output_dir),
            "packages": len(package_records),
            "pages": sum(item["pages"] for item in package_records),
            "duration_seconds": round(time.monotonic() - started, 2),
        }
        self.log("Consolidação concluída.")
        return result
