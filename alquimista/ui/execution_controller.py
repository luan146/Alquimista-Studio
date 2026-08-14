"""Compatibility facade for alquimista.ui.controllers.execution_controller."""
from __future__ import annotations

from .controllers.execution_controller import (
    execute_selected_operation,
    prepare_runtimes,
    retry_failures,
    run_complete,
    run_consolidation,
    run_extraction,
    validated_project_snapshot,
)

__all__ = [
    "execute_selected_operation",
    "prepare_runtimes",
    "retry_failures",
    "run_complete",
    "run_consolidation",
    "run_extraction",
    "validated_project_snapshot",
]
