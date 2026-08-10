from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..selection import SelectionStore


@dataclass
class MainWindowState:
    """Mutable application state kept outside Qt widgets."""

    trees: dict[str, dict[str, Any]] = field(default_factory=dict)
    selection_store: SelectionStore = field(default_factory=SelectionStore)
    connected_sources: set[str] = field(default_factory=set)
    connection_states: dict[str, str] = field(default_factory=dict)
    last_result: dict[str, Any] = field(default_factory=dict)
    last_consolidation_preview: list[dict[str, Any]] = field(default_factory=list)
    operation_status: str = "IDLE"
    operation_error: str = ""
