"""Compatibility facade for alquimista.ui.controllers.source_controller."""
from __future__ import annotations

from .controllers.source_controller import (
    ComboDataProvider,
    build_source_snapshot,
    build_source_snapshots,
    normalize_source_config,
    source_by_combo,
    source_by_identifier,
    source_by_index,
)

__all__ = [
    "ComboDataProvider",
    "build_source_snapshot",
    "build_source_snapshots",
    "normalize_source_config",
    "source_by_combo",
    "source_by_identifier",
    "source_by_index",
]
