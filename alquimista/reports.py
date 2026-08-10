from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import Field

from .models import Model


class DocumentResult(Model):
    source_id: str
    source_type: str
    container_id: str = ""
    document_id: str = ""
    title: str = ""
    status: str = ""
    error: str = ""
    markdown_path: str = ""


class ContainerReport(Model):
    source_id: str
    source_type: str
    container_id: str
    name: str
    documents_found: int = 0
    documents_selected: int = 0
    documents: list[DocumentResult] = Field(default_factory=list)


class SourceReport(Model):
    source_id: str
    source_type: str
    name: str
    containers: list[ContainerReport] = Field(default_factory=list)


class ExecutionReport(Model):
    """Stable report shape used by the UI, JSON output and future exporters."""

    schema_version: int = 1
    run_id: str = ""
    project: str = ""
    executed_at: str = ""
    duration_seconds: float = 0.0
    output_dir: str = ""
    manifest: str = ""
    sources: list[SourceReport] = Field(default_factory=list)
    pages_found: int = 0
    pages_selected: int = 0
    counters: dict[str, int] = Field(default_factory=dict)
    failures: int = 0
    throttling_events: int = 0

    @classmethod
    def start(cls, project: str, output_dir: str, manifest: str) -> "ExecutionReport":
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        return cls(
            run_id=f"run-{stamp}",
            project=project,
            executed_at=datetime.now().astimezone().isoformat(timespec="seconds"),
            output_dir=output_dir,
            manifest=manifest,
        )

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
