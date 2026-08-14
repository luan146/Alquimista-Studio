from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import EntryStatus, ProjectConfig, now_iso
from ..runtime import CancellationToken, LogCallback
from ..storage import MANIFEST_NAME, ManifestStore
from .runtime import SourceRuntime


class InventoryReconciliationService:
    """Explicit, body-free remote inventory reconciliation action."""

    def __init__(
        self,
        project: ProjectConfig,
        runtimes: list[SourceRuntime],
        project_dir: Path,
        *,
        token: CancellationToken | None = None,
        log: LogCallback | None = None,
    ) -> None:
        self.project = project
        self.runtimes = runtimes
        self.project_dir = project_dir.resolve()
        self.token = token or CancellationToken()
        self.log = log or (lambda _message: None)
        output_dir = Path(project.output_dir)
        self.output_dir = (
            output_dir if output_dir.is_absolute() else self.project_dir / output_dir
        ).resolve()
        self.store = ManifestStore(self.output_dir / MANIFEST_NAME, project, log=self.log)

    def run(self) -> dict[str, Any]:
        manifest = self.store.load()
        discovered: set[tuple[str, str, str]] = set()
        completed_containers: set[tuple[str, str]] = set()
        failures: list[dict[str, str]] = []
        for runtime in self.runtimes:
            connector = runtime.connector
            if connector is None:
                continue
            try:
                self.token.check()
                for container in connector.list_containers():
                    container_id = str(container.id)
                    self.token.check()
                    try:
                        metadata = connector.list_documents(container_id)
                    except Exception as exc:
                        failures.append(
                            {
                                "source_id": runtime.source.id,
                                "container_id": container_id,
                                "error": str(exc),
                            }
                        )
                        continue
                    for item in metadata:
                        discovered.add((runtime.source.id, container_id, str(item.id)))
                    completed_containers.add((runtime.source.id, container_id))
            finally:
                connector.close()
        removed = 0
        for entry in manifest.entries:
            identity = (
                entry.source_id,
                str(entry.container_id or entry.space_key),
                str(entry.document_id or entry.page_id),
            )
            if (
                identity[:2] in completed_containers
                and identity not in discovered
                and entry.active
            ):
                entry.active = False
                entry.status = EntryStatus.REMOVED
                entry.checked_at = now_iso()
                removed += 1
        self.store.save(manifest)
        report = {
            "completed_containers": len(completed_containers),
            "removed": removed,
            "failures": failures,
            "generated_at": now_iso(),
        }
        self.log(f"Reconciliação concluída: {removed} remoções.")
        return report


__all__ = ["InventoryReconciliationService"]
