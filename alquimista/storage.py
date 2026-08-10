from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .errors import InvalidProjectError, ManifestError, StorageError
from .manifest_index import ManifestIndex
from .models import ManifestDocument, ManifestEntry, ProjectConfig, now_iso

MANIFEST_NAME = "manifesto_alquimista.json"
MANIFEST_INDEX_NAME = "indice_manifesto_alquimista.sqlite3"
FAILURES_NAME = "falhas_alquimista.json"
REPORT_NAME = "relatorio_execucao_alquimista.json"
PACKAGE_INDEX_NAME = "indice_pacotes_alquimista.json"


def confined_path(base: Path, relative: str | Path) -> Path:
    base = base.resolve()
    candidate = (base / relative).resolve()
    if candidate != base and base not in candidate.parents:
        raise StorageError(f"O caminho sai da pasta permitida: {relative}")
    return candidate


def atomic_write_text(path: Path, content: str, *, backup: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        fd, raw = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        temporary = Path(raw)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        if backup and path.exists():
            shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        os.replace(temporary, path)
    except OSError as exc:
        raise StorageError(f"Não foi possível gravar {path}: {exc}") from exc
    finally:
        if temporary and temporary.exists():
            temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, data: Any, *, backup: bool = False) -> None:
    atomic_write_text(
        path,
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        backup=backup,
    )


class FileTransaction:
    """Stage related file changes and roll back a failed in-process commit."""

    def __init__(self, base: Path) -> None:
        self.base = base.resolve()
        self.base.mkdir(parents=True, exist_ok=True)
        self.directory = Path(
            tempfile.mkdtemp(prefix=".alquimista-txn-", dir=self.base)
        )
        self.staged: dict[Path, Path] = {}
        self.deletions: set[Path] = set()
        self._committed = False
        self._rollback_failed = False

    def _target(self, path: Path) -> Path:
        resolved = path.resolve()
        if resolved != self.base and self.base not in resolved.parents:
            raise StorageError(f"O caminho sai da transação permitida: {path}")
        return resolved

    def stage_text(self, path: Path, content: str) -> None:
        target = self._target(path)
        staged = self.directory / "staged" / f"{uuid.uuid4().hex}.tmp"
        atomic_write_text(staged, content)
        previous = self.staged.get(target)
        if previous:
            previous.unlink(missing_ok=True)
        self.staged[target] = staged
        self.deletions.discard(target)

    def stage_json(self, path: Path, data: Any) -> None:
        self.stage_text(
            path,
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        )

    def stage_delete(self, path: Path) -> None:
        target = self._target(path)
        staged = self.staged.pop(target, None)
        if staged:
            staged.unlink(missing_ok=True)
        self.deletions.add(target)

    def commit(self) -> None:
        backups = self.directory / "backups"
        # Each rollback entry records (target, backup, existed_before, kind)
        # so rollback is deterministic even when a later operation fails.
        applied: list[tuple[Path, Path | None, bool, str]] = []
        try:
            operations = [
                (target, staged)
                for target, staged in sorted(
                    self.staged.items(), key=lambda item: str(item[0])
                )
            ]
            for target, staged in operations:
                target.parent.mkdir(parents=True, exist_ok=True)
                existed_before = target.exists()
                backup: Path | None = None
                if existed_before:
                    backup = backups / f"{uuid.uuid4().hex}.bak"
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(target, backup)
                applied.append((target, backup, existed_before, "publish"))
                os.replace(staged, target)
            for target in sorted(self.deletions, key=str):
                if target.exists():
                    backup = backups / f"{uuid.uuid4().hex}.bak"
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(target, backup)
                    applied.append((target, backup, True, "delete"))
            self._committed = True
        except OSError as exc:
            rollback_errors: list[str] = []
            for target, backup, existed_before, kind in reversed(applied):
                try:
                    if kind == "publish":
                        # If this transaction created the target, remove the
                        # published copy so the pre-transaction state (absent)
                        # is restored. Otherwise restore the original via
                        # os.replace, which atomically overwrites whatever the
                        # failed publish left in place.
                        if existed_before and backup and backup.exists():
                            target.parent.mkdir(parents=True, exist_ok=True)
                            os.replace(backup, target)
                        else:
                            target.unlink(missing_ok=True)
                    else:  # deletion rollback
                        if backup and backup.exists():
                            target.parent.mkdir(parents=True, exist_ok=True)
                            os.replace(backup, target)
                except OSError as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
            detail = (
                f" Rollback incompleto: {'; '.join(rollback_errors)}"
                if rollback_errors
                else ""
            )
            message = f"Falha ao publicar a transação de arquivos: {exc}.{detail}"
            if rollback_errors:
                # Rollback failed: preserve the transaction directory and any
                # remaining backups/staged files for manual recovery instead
                # of destroying evidence via close().
                message += (
                    f" Backups preservados em: {self.directory}"
                )
                self._rollback_failed = True
                raise StorageError(message) from exc
            raise StorageError(message) from exc
        finally:
            if self._committed:
                self.close()

    def close(self) -> None:
        # When rollback failed we intentionally keep the transaction directory
        # (and the backups/staged files it contains) so operators can recover
        # the original content manually.
        if getattr(self, "_rollback_failed", False):
            return
        if self.directory.exists():
            shutil.rmtree(self.directory, ignore_errors=True)

    def __enter__(self) -> "FileTransaction":
        return self

    def __exit__(self, *_args: Any) -> None:
        self.close()


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StorageError(f"JSON inválido ou inacessível: {path}") from exc


def save_project(path: Path, project: ProjectConfig) -> None:
    atomic_write_json(path, project.to_dict(), backup=path.exists())


def load_project(path: Path) -> ProjectConfig:
    try:
        data = load_json(path)
        if not isinstance(data, dict):
            raise InvalidProjectError("O arquivo de projeto deve conter um objeto JSON.")
        return ProjectConfig.from_dict(data)
    except Exception as exc:
        if isinstance(exc, InvalidProjectError):
            raise
        raise InvalidProjectError(f"Projeto inválido: {exc}") from exc


class ManifestStore:
    def __init__(
        self,
        path: Path,
        project: ProjectConfig,
        *,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.path = path
        self.project = project
        self.log = log or (lambda _message: None)
        self.index = ManifestIndex(path.with_name(MANIFEST_INDEX_NAME))

    def load(self) -> ManifestDocument:
        self.log(f"[Manifesto] Lendo {self.path} (existe={self.path.exists()})")
        if not self.path.exists():
            self.log("[Manifesto] Arquivo ainda não existe; retornando manifesto vazio.")
            return ManifestDocument(project_id=self.project.project_id, project_name=self.project.project_name)
        try:
            raw = load_json(self.path)
            if isinstance(raw, list):
                entries: list[ManifestEntry] = []
                for item in raw:
                    converted = dict(item)
                    converted["page_id"] = str(converted.pop("id", converted.get("page_id", "")))
                    converted["root_page_id"] = str(converted.pop("root_id", converted.get("root_page_id", "")))
                    source = next(
                        (candidate for candidate in self.project.sources
                         if candidate.id == converted.get("source_id")),
                        None,
                    )
                    container_id = str(
                        converted.get("container_id")
                        or converted.get("space_key")
                        or (source.space_key if source else "__legacy__")
                    )
                    converted.setdefault("source_type", source.source_type if source else "confluence_rest")
                    converted.setdefault("container_id", container_id)
                    converted.setdefault("container_name", converted.get("space_name", ""))
                    converted.setdefault("document_id", converted["page_id"])
                    if source and source.space_key:
                        converted["document_key"] = f"{converted.get('source_id', '')}:{container_id}:{converted['page_id']}"
                    converted["metadata_hash"] = converted.pop("metadata_signature", "")
                    converted["transform_config_hash"] = converted.pop("format_signature", "")
                    package = converted.pop("package", None)
                    converted["packages"] = [package] if package else []
                    converted.setdefault("first_collected_at", converted.get("collected_at"))
                    converted.setdefault("last_successful_at", converted.get("collected_at"))
                    entries.append(ManifestEntry.model_validate(converted))
                document = ManifestDocument(
                    project_id=self.project.project_id,
                    project_name=self.project.project_name,
                    generated_at=now_iso(),
                    entries=entries,
                )
                self.log(f"[Manifesto] Formato legado carregado: {len(entries)} entradas.")
                return document
            if isinstance(raw, dict):
                migrated = dict(raw)
                raw_schema_version = int(migrated.get("schema_version", 3))
                migrated_entries: list[dict[str, Any]] = []
                for item in migrated.get("entries", []) or []:
                    converted = dict(item)
                    source = next(
                        (candidate for candidate in self.project.sources
                         if candidate.id == converted.get("source_id")),
                        None,
                    )
                    page_id = str(converted.get("page_id") or converted.get("document_id") or "")
                    container_id = str(
                        converted.get("container_id")
                        or converted.get("space_key")
                        or (source.space_key if source else "__legacy__")
                    )
                    converted.setdefault("source_type", source.source_type if source else "confluence_rest")
                    converted.setdefault("container_id", container_id)
                    converted.setdefault("container_name", converted.get("space_name", ""))
                    converted.setdefault("document_id", page_id)
                    if raw_schema_version < 4 and source and source.space_key and converted.get("document_key", "").count(":") < 2:
                        converted["document_key"] = f"{converted.get('source_id', '')}:{container_id}:{page_id}"
                    migrated_entries.append(converted)
                migrated["entries"] = migrated_entries
                migrated["schema_version"] = max(int(migrated.get("schema_version", 3)), 4)
                document = ManifestDocument.model_validate(migrated)
                self.log(
                    f"[Manifesto] Schema {document.schema_version} carregado: "
                    f"{len(document.entries)} entradas."
                )
                return document
            document = ManifestDocument.model_validate(raw)
            self.log(f"[Manifesto] Carregado: {len(document.entries)} entradas.")
            return document
        except Exception as exc:
            self.log(f"[Manifesto] Falha ao ler {self.path}: {exc}")
            raise ManifestError(f"Manifesto inválido em {self.path}: {exc}") from exc

    def save(self, document: ManifestDocument) -> None:
        document.generated_at = now_iso()
        self.log(f"[Manifesto] Gravando {self.path} ({len(document.entries)} entradas).")
        atomic_write_json(self.path, document.model_dump(mode="json"), backup=self.path.exists())
        self.index.rebuild(document)
