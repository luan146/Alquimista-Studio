from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..errors import AlquimistaError, ManifestError, StorageError
from ..markdown import normalize_markdown
from ..models import (
    EntryStatus,
    ManifestDocument,
    ManifestEntry,
    ProjectConfig,
    now_iso,
    stable_json_hash,
)
from ..runtime import CancellationToken, LogCallback, ProgressCallback
from ..storage import (
    MANIFEST_NAME,
    PACKAGE_INDEX_NAME,
    FileTransaction,
    ManifestStore,
    confined_path,
)
from .helpers import demote_headings, sanitize_filename


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
        return sorted(
            entries,
            key=lambda item: ([p.casefold() for p in item.path], item.title.casefold()),
        )

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
                    identifier = (
                        f"`DOC-{entry.page_id}` — "
                        if options.include_ids_in_index
                        else ""
                    )
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


__all__ = ["ConsolidationService"]
