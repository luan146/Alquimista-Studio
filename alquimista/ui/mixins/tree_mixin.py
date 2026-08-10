"""Tree management mixin for MainWindow.

This mixin provides all tree-related functionality including:
- Tree data management
- Page tree population
- Selection tree population  
- Lazy loading support
- Document expansion
"""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem

from ..models import SourceConfig
from ..tree_models import (
    explicit_visibility_kind,
    tree_containers,
    tree_pages,
    visibility_for_page,
)
from ..tree_models import (
    lazy_state as tree_lazy_state,
)
from ..tree_models import (
    page_container_id as tree_page_container_id,
)


class TreeMixin:
    """Mixin providing tree management functionality."""

    # These will be provided by MainWindow
    _trees: dict[str, dict[str, Any]]
    _page_render_limits: dict[tuple[str, str], int]
    _selection_render_limits: dict[tuple[str, str], int]
    _active_page_container: str | None
    _active_selection_container: str | None
    project: Any
    page_tree: QTreeWidget
    selection_tree: QTreeWidget
    tree_empty: Any
    page_load_more_button: Any
    selection_load_more_button: Any
    page_render_status: Any
    selection_render_status: Any

    @property
    def trees(self) -> dict[str, dict[str, Any]]:
        """Return the current tree data store."""
        return self._trees

    @staticmethod
    def _page_container_id(source: SourceConfig, page: dict[str, Any]) -> str:
        """Get container ID for a page."""
        return tree_page_container_id(source, page)

    def _tree_pages(
        self, data: dict[str, Any], container_id: str | None = None
    ) -> list[dict[str, Any]]:
        """Get pages from tree data."""
        return tree_pages(data, container_id)

    def _tree_containers(
        self, source: SourceConfig, data: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Get containers from tree data."""
        return tree_containers(source, data)

    def _container_loaded(
        self, source: SourceConfig, data: dict[str, Any], container_id: str
    ) -> bool:
        """Check if container is already loaded."""
        if str(container_id) in (data.get("pages_by_container") or {}):
            return True
        return any(
            self._page_container_id(source, page) == str(container_id)
            for page in data.get("pages", [])
        )

    @staticmethod
    def _container_requires_full_load(data: dict[str, Any], container_id: str) -> bool:
        """Return whether current snapshot contains roots only."""
        state_value = (data.get("lazy_discovery") or {}).get(str(container_id) or {})
        state = state_value if isinstance(state_value, dict) else {}
        return bool(state.get("enabled") and not state.get("full_loaded"))

    @staticmethod
    def _lazy_state(data: dict[str, Any], container_id: str) -> dict[str, Any]:
        """Get lazy discovery state for container."""
        return tree_lazy_state(data, container_id)

    @staticmethod
    def _lazy_method(connector: Any, operation: str) -> Any:
        """Return optional lazy-discovery method without weakening legacy connectors."""
        service = getattr(connector, "lazy_service", None) or getattr(
            connector, "discovery_service", None
        )
        if service:
            return getattr(service, operation, None)
        return None

    def _page_visibility(self, source: SourceConfig, page: dict[str, Any]) -> tuple[str, str]:
        """Get visibility for page."""
        return visibility_for_page(source, page)

    @staticmethod
    def _explicit_visibility_kind(page: dict[str, Any]) -> str | None:
        """Get explicit visibility kind from page."""
        return explicit_visibility_kind(page)

    def _leaf_items(self) -> list[QTreeWidgetItem]:
        """Get all leaf items from selection tree."""
        leaves: list[QTreeWidgetItem] = []

        def walk(item: QTreeWidgetItem) -> None:
            if item.childCount() == 0 and item.text(1):
                leaves.append(item)
            for i in range(item.childCount()):
                walk(item.child(i))

        for index in range(self.selection_tree.topLevelItemCount()):
            item = self.selection_tree.topLevelItem(index)
            if item is not None:
                walk(item)
        return leaves
