from __future__ import annotations

from typing import Any

from alquimista.models import AuthMode
from alquimista.ui.components import VisibilityBadgeDelegate
from alquimista.ui.main_window import MainWindow


def _page(document_id: str, title: str, *, has_children: bool = False) -> dict[str, Any]:
    return {
        "id": document_id,
        "title": title,
        "type": "page",
        "_container_id": "space-a",
        "parent_id": None,
        "has_children": has_children,
        "visibility": "public",
        "version": {},
    }


def test_authenticated_page_without_visibility_metadata_is_unknown(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    source.auth_mode = AuthMode.BASIC

    assert window._page_visibility(source, {"id": "page-a", "title": "Página"}) == (
        "Desconhecida",
        "unknown",
    )


def test_tree_loading_shows_persistent_progress_on_pages_screen(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    window.show()

    window._set_tree_loading(True, "Carregando páginas…")

    # The dashboard is the initial page, so QWidget.isVisible() also depends
    # on the hidden ancestor. isHidden() verifies the loading state itself.
    assert not window.tree_load_progress.isHidden()
    assert window.tree_load_progress.minimum() == 0
    assert window.tree_load_progress.maximum() == 0
    assert "Carregando páginas" in window.tree_load_status.text()

    window._on_progress(1, 4, "Espaço A")

    assert window.tree_load_progress.maximum() == 100
    assert window.tree_load_progress.value() == 25
    assert "Espaço A" in window.tree_load_status.text()

    window._set_tree_loading(False, "4 páginas carregadas.")

    assert not window.tree_load_progress.isVisible()
    assert window.tree_load_status.text() == "4 páginas carregadas."


def test_page_title_cell_has_one_painting_source(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    data = {
        "root": {"id": "root", "title": "Manual"},
        "pages": [_page("page-a", "Página única")],
    }

    window._populate_page_tree(source, data)
    item = window.page_tree.topLevelItem(0)

    assert item is not None
    assert window.page_tree.itemWidget(item, 0) is None
    assert item.data(0, VisibilityBadgeDelegate.TITLE_ROLE) == "Página única"
    assert item.data(0, VisibilityBadgeDelegate.ICON_ROLE) == "📄"


class _LazyConnectorDouble:
    def __init__(self) -> None:
        self.children_calls: list[tuple[str, str]] = []

    def list_document_children(
        self,
        container_id: str,
        parent_id: str,
        **_kwargs: Any,
    ) -> list[dict[str, Any]]:
        self.children_calls.append((container_id, parent_id))
        return [
            {
                "id": "child-a-1",
                "title": "Filho de A",
                "type": "page",
                "parent_id": parent_id,
                "has_children": False,
                "visibility": "public",
            }
        ]

    def close(self) -> None:
        return None


def test_expanding_parent_loads_only_that_parent_children(qtbot, monkeypatch) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    connector = _LazyConnectorDouble()
    monkeypatch.setattr(window.connector_registry, "create", lambda *_args, **_kwargs: connector)
    data = {
        "root": {"id": "root", "title": "Manual"},
        "containers": [{"id": "space-a", "key": "space-a", "name": "Manual"}],
        "pages_by_container": {
            "space-a": [
                _page("parent-a", "Pai A", has_children=True),
                _page("parent-b", "Pai B", has_children=True),
            ]
        },
        "lazy_discovery": {
            "space-a": {"enabled": True, "loaded_parents": [], "fallback_reason": ""}
        },
    }
    window.trees[source.id] = data
    window._active_page_container = "space-a"
    window._populate_page_tree(source, data, container_id="space-a")
    parent_a = next(
        window.page_tree.topLevelItem(index)
        for index in range(window.page_tree.topLevelItemCount())
        if window.page_tree.topLevelItem(index).text(0) == "Pai A"
    )

    parent_a.setExpanded(True)
    qtbot.waitUntil(lambda: window.worker is None, timeout=3000)

    assert connector.children_calls == [("space-a", "parent-a")]
    assert any(page["id"] == "child-a-1" for page in data["pages_by_container"]["space-a"])
