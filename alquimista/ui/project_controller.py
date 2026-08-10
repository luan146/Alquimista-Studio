"""Pure project-management helpers used by the Qt window.

This module deliberately contains no Qt dependency.  ``MainWindow`` remains
the owner of UI state and user-facing error handling while these helpers keep
path resolution, validation, and storage delegation independently testable.
"""

from __future__ import annotations

from pathlib import Path

from ..models import ProjectConfig
from ..storage import load_project, save_project


def resolve_project_dir(
    project_path: Path | None,
    *,
    current_dir: Path | None = None,
) -> Path:
    """Return the base directory used by project-relative operations."""

    if project_path is not None:
        return project_path.parent
    return current_dir if current_dir is not None else Path.cwd()


def validate_project_snapshot(project: ProjectConfig) -> ProjectConfig:
    """Create a validated, detached snapshot of ``project``."""

    return ProjectConfig.from_dict(project.to_dict())


def load_project_file(path: Path) -> ProjectConfig:
    """Load and validate a project through the existing storage boundary."""

    return load_project(path)


def save_project_file(path: Path, project: ProjectConfig) -> None:
    """Persist a project through the existing atomic storage implementation."""

    save_project(path, project)
