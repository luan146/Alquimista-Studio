"""Compatibility facade for alquimista.ui.controllers.project_controller."""
from __future__ import annotations

from .controllers.project_controller import (
    load_project_file,
    resolve_project_dir,
    save_project_file,
    validate_project_snapshot,
)

__all__ = [
    "load_project_file",
    "resolve_project_dir",
    "save_project_file",
    "validate_project_snapshot",
]
