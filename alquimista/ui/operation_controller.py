"""Compatibility facade for alquimista.ui.controllers.operation_controller."""
from __future__ import annotations

from .controllers.operation_controller import (
    DoneCallback,
    OperationController,
    WorkerFunction,
    WorkerOperationController,
    _connection_error_presentation,
)

__all__ = [
    "DoneCallback",
    "OperationController",
    "WorkerFunction",
    "WorkerOperationController",
    "_connection_error_presentation",
]
