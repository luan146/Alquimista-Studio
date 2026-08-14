from __future__ import annotations

from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import (
    QFileDialog,
    QMessageBox,
    QPushButton,
    QStyle,
    QStyleOptionViewItem,
    QTreeWidget,
    QTreeWidgetItem,
)

from alquimista.models import AuthMode
from alquimista.ui.components import SourceCard, VisibilityBadgeDelegate
from alquimista.ui.main_window import MainWindow
from alquimista.ui.tree_models import ordered_pages


@pytest.mark.parametrize("mode", ["complete", "extractor", "consolidator"])
def test_three_modes_open(qtbot, mode: str) -> None:
    window = MainWindow(mode)
    qtbot.addWidget(window)
    window.show()
    assert window.windowTitle().startswith("ALQuimista Studio")
    assert window.stack.count() >= 4
    window.dirty = False


@pytest.mark.parametrize(
    ("source_type", "expected_platform"),
    [
        ("confluence_rest", "confluence_rest"),
        ("zendesk_guide", "zendesk_guide"),
        ("notion_api", "notion_api"),
        ("sharepoint_graph", "sharepoint_graph"),
        ("gitbook_api", "gitbook_api"),
        ("generic_web", "generic_web"),
        ("generic_docs", "generic_docs"),
        ("local_files", "local_files"),
        ("bookstack_api", "bookstack_api"),
        ("github_docs", "github_docs"),
        ("gitlab_docs", "gitlab_docs"),
        ("freshdesk_solutions", "freshdesk_solutions"),
        ("intercom_api", "intercom_api"),
        ("salesforce_api", "salesforce_api"),
        ("hubspot_api", "hubspot_api"),
        ("helpscout_docs", "helpscout_docs"),
        ("document360_api", "document360_api"),
        ("outline_api", "outline_api"),
        ("helpjuice_api", "helpjuice_api"),
        ("guru_api", "guru_api"),
        ("slite_api", "slite_api"),
        ("mediawiki_api", "mediawiki_api"),
        ("readme_api", "readme_api"),
        ("wordpress_api", "wordpress_api"),
        ("ghost_api", "ghost_api"),
        ("strapi_api", "strapi_api"),
        ("contentful_api", "contentful_api"),
        ("sanity_api", "sanity_api"),
    ],
)
def test_dashboard_source_cards_open_sources_page(
    qtbot, source_type: str, expected_platform: str
) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)

    cards = {
        card.source_type: card
        for card in window.pages["dashboard"].findChildren(SourceCard)
    }
    assert set(cards) == {
        "confluence_rest",
        "zendesk_guide",
        "notion_api",
        "sharepoint_graph",
        "gitbook_api",
        "generic_web",
        "generic_docs",
        "local_files",
        "bookstack_api",
        "github_docs",
        "gitlab_docs",
        "freshdesk_solutions",
        "intercom_api",
        "salesforce_api",
        "hubspot_api",
        "helpscout_docs",
        "document360_api",
        "outline_api",
        "helpjuice_api",
        "guru_api",
        "slite_api",
        "mediawiki_api",
        "readme_api",
        "wordpress_api",
        "ghost_api",
        "strapi_api",
        "contentful_api",
        "sanity_api",
    }


    qtbot.mouseClick(cards[source_type], Qt.MouseButton.LeftButton)

    assert window.stack.currentWidget() is window.pages["sources"]
    assert window.src_platform.currentData() == expected_platform
    window.dirty = False


def test_top_bar_keeps_only_save_action(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)

    top_bar = window.top_project.parentWidget()
    assert [button.text() for button in top_bar.findChildren(QPushButton)] == [
        "Configurações",
        "Salvar",
    ]
    window.dirty = False


def test_source_crud_and_markdown_preview(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    original = len(window.project.sources)
    window.add_source()
    assert len(window.project.sources) == original + 1
    window.src_name.setText("Documentação interna")
    window.src_url.setText("https://example.test")
    window.src_root.setText("Manual")
    window.apply_source()
    assert window.current_source().name == "Documentação interna"
    window._apply_preset("rag")
    assert window.project.markdown.metadata_style == "yaml"
    assert "title:" in window.preview_after.toPlainText()
    window.dirty = False


def test_url_first_source_form_add_edit_and_remove(
    qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)

    window.source_url_input.setText("https://docs.example.com/display/DOC/Manual+interno")
    window.source_name_input.setText("Manual interno")
    window._commit_source_from_form()

    source = window.project.sources[0]
    assert source.source_type == "confluence_rest"
    assert source.space_key == "DOC"
    assert source.connector_options["source_url"].endswith("Manual+interno")
    assert window.source_table.rowCount() == 1
    assert "Confluence" in window.source_table.item(0, 3).text()

    window._edit_source_row(0)
    window.source_url_input.setText("https://www.notion.so/acme/Manual-123")
    window.source_name_input.setText("Manual Notion")
    window._commit_source_from_form()
    assert window.project.sources[0].source_type == "notion_api"
    assert window.project.sources[0].name == "Manual Notion"

    window.source_table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.remove_selected_sources()
    assert window.source_table.rowCount() == 0
    assert not window.project.sources
    window.dirty = False


def test_source_url_autofill(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    window.src_url.setText(
        "https://docs.example.com/display/DEMO/Getting+Started"
    )
    window._autofill_source_url()
    assert window.src_url.text() == "https://docs.example.com"
    assert window.src_space.text() == "DEMO"
    assert window.src_root_mode.currentData() == "title"
    assert window.src_root.text() == "Getting Started"
    assert window.current_source().root_mode == "title"
    assert window.current_source().space_key == "DEMO"
    assert "identificados" in window.src_autofill_status.text()
    window.dirty = False


def test_tree_columns_use_interactive_resize_and_typed_sort(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    data = {
        "root": {"id": "100", "title": "Manual"},
        "pages": [
            {"id": "2", "title": "B", "version": {"number": 2, "when": "2024-01-01T00:00:00Z"}},
            {"id": "10", "title": "A", "version": {"number": 10, "when": "2025-01-01T00:00:00Z"}},
        ],
    }
    window._populate_page_tree(source, data)
    window.page_tree.sortItems(5, Qt.SortOrder.DescendingOrder)
    assert window.page_tree.topLevelItem(0).text(5) == "10"
    assert (
        window.page_tree.header().sectionResizeMode(0)
        == window.page_tree.header().ResizeMode.Interactive
    )
    window.dirty = False


def test_selection_header_toggles_sort_on_repeated_clicks(qtbot) -> None:
    """Repeated clicks on the same selection header flip ascending/descending."""
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    pages = [
        {"id": "5", "title": "Zebra", "_container_id": "space-a"},
        {"id": "10", "title": "Abacate", "_container_id": "space-a"},
        {"id": "7", "title": "Manga", "_container_id": "space-a"},
    ]
    data = {
        "root": {"id": "1", "title": "Raiz"},
        "containers": [{"id": "space-a", "name": "A"}],
        "pages_by_container": {"space-a": pages},
    }
    window._populate_selection_tree(source, data, container_id="space-a")
    tree = window.selection_tree
    header = tree.header()
    # Header must remain clickable and show the sort indicator after populate.
    assert header.sectionsClickable() is True
    assert header.isSortIndicatorShown() is True
    # SortIndicatorClearable must be False so repeated clicks toggle, not clear.
    if hasattr(header, "isSortIndicatorClearable"):
        assert header.isSortIndicatorClearable() is False
    # 1st click on Page ID -> ascending (numeric: 5, 7, 10)
    header.sectionClicked.emit(1)
    assert header.sortIndicatorSection() == 1
    assert header.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder
    assert tree.topLevelItem(0).text(1) == "5"
    assert tree.topLevelItem(2).text(1) == "10"
    # 2nd click -> descending (10, 7, 5)
    header.sectionClicked.emit(1)
    assert header.sortIndicatorOrder() == Qt.SortOrder.DescendingOrder
    assert tree.topLevelItem(0).text(1) == "10"
    assert tree.topLevelItem(2).text(1) == "5"
    # 3rd click -> ascending again
    header.sectionClicked.emit(1)
    assert header.sortIndicatorOrder() == Qt.SortOrder.AscendingOrder
    assert tree.topLevelItem(0).text(1) == "5"
    # Header stays interactive across clicks.
    assert header.sectionsClickable() is True
    assert header.isSortIndicatorShown() is True
    window.dirty = False


def test_page_tree_renders_hierarchy_and_visibility_badges(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    source.auth_mode = AuthMode.BASIC
    data = {
        "root": {"id": "100", "title": "Manual"},
        "loaded_at": "2026-07-30T10:45:00-03:00",
        "pages": [
            {
                "id": "101",
                "title": "Pasta pública",
                "ancestors": [{"id": "200", "title": "Suporte"}],
                "public": True,
                "version": {"number": 2, "when": "2026-07-30T10:21:00Z"},
            },
            {
                "id": "102",
                "title": "Página privada",
                "ancestors": [{"id": "200", "title": "Suporte"}],
                "private": True,
                "version": {"number": 1, "when": "2026-07-30T10:20:00Z"},
            },
        ],
    }

    window._populate_page_tree(source, data)

    root = next(
        window.page_tree.topLevelItem(index)
        for index in range(window.page_tree.topLevelItemCount())
        if window.page_tree.topLevelItem(index).text(0) == "Suporte"
    )
    assert root is not None
    assert root.text(0) == "Suporte"
    assert root.childCount() == 2
    assert window.page_tree.header().sectionsMovable()
    assert window.page_tree.header().sectionsClickable()
    assert root.data(0, VisibilityBadgeDelegate.TITLE_ROLE) == "Suporte"
    assert root.data(0, VisibilityBadgeDelegate.VISIBILITY_ROLE) == "Raiz"
    child_badges = [
        root.child(index).data(0, VisibilityBadgeDelegate.VISIBILITY_ROLE)
        for index in range(root.childCount())
    ]
    page_labels = child_badges
    assert "Pública" in page_labels
    window.dirty = False


def test_page_tree_attaches_child_to_real_parent_when_parent_arrives_later(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    data = {
        "root": {"id": "100", "title": "Manual"},
        "pages": [
            {
                "id": "child",
                "title": "Filho",
                "parent_id": "parent",
                "ancestors": [
                    {"id": "100", "title": "Manual"},
                    {"id": "parent", "title": "Pai"},
                ],
            },
            {"id": "parent", "title": "Pai", "ancestors": [{"id": "100", "title": "Manual"}]},
        ],
    }

    window._populate_page_tree(source, data)

    parent = window.page_tree.topLevelItem(0)
    assert parent is not None
    assert parent.text(0) == "Pai"
    assert parent.childCount() == 1
    assert parent.child(0).text(0) == "Filho"
    window.dirty = False


def test_selection_tree_attaches_child_to_real_parent_when_parent_arrives_later(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    data = {
        "root": {"id": "100", "title": "Manual"},
        "pages": [
            {
                "id": "child",
                "title": "Filho",
                "parent_id": "parent",
                "ancestors": [
                    {"id": "100", "title": "Manual"},
                    {"id": "parent", "title": "Pai"},
                ],
            },
            {"id": "parent", "title": "Pai", "ancestors": [{"id": "100", "title": "Manual"}]},
        ],
    }

    window._populate_selection_tree(source, data)

    parent = window.selection_tree.topLevelItem(0)
    assert parent is not None
    assert parent.text(0).endswith("Pai")
    assert parent.childCount() == 1
    assert parent.child(0).text(0).endswith("Filho")
    window.dirty = False


def test_page_visibility_uses_public_auth_mode_without_inference_for_authenticated_sources(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    page = {"id": "101", "title": "Página sem sinalização de acesso"}

    source.auth_mode = AuthMode.PUBLIC
    assert window._page_visibility(source, page) == ("Pública", "public")

    source.auth_mode = AuthMode.BASIC
    assert window._page_visibility(source, page) == ("Desconhecida", "unknown")
    window.dirty = False


def test_visibility_badge_delegate_clips_cell_and_does_not_duplicate_title(
    qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = QTreeWidget()
    qtbot.addWidget(tree)
    tree.setColumnCount(1)
    item = QTreeWidgetItem(["Título original que não deve ser redesenhado"])
    tree.addTopLevelItem(item)
    item.setData(
        0,
        VisibilityBadgeDelegate.TITLE_ROLE,
        "Um título muito comprido que precisa ser elidido",
    )
    item.setData(0, VisibilityBadgeDelegate.ICON_ROLE, "📄")
    item.setData(0, VisibilityBadgeDelegate.VISIBILITY_ROLE, "Pública")
    item.setData(0, VisibilityBadgeDelegate.VISIBILITY_KIND_ROLE, "public")

    def inherited_paint_would_duplicate_title(*args: object, **kwargs: object) -> None:
        raise AssertionError("o delegate base não deve redesenhar o título do modelo")

    monkeypatch.setattr(
        "PySide6.QtWidgets.QStyledItemDelegate.paint",
        inherited_paint_would_duplicate_title,
    )

    image = QImage(260, 48, QImage.Format.Format_ARGB32_Premultiplied)
    sentinel = QColor("#123456")
    image.fill(sentinel)
    painter = QPainter(image)
    option = QStyleOptionViewItem()
    option.rect.setRect(12, 8, 120, 28)
    option.widget = tree
    option.state = QStyle.StateFlag.State_Enabled
    VisibilityBadgeDelegate(tree).paint(painter, option, tree.indexFromItem(item))
    painter.end()

    assert image.pixelColor(0, 0) == sentinel
    assert image.pixelColor(140, 20) == sentinel
    assert any(
        image.pixelColor(x, y) != sentinel
        for x in range(option.rect.left(), option.rect.right() + 1)
        for y in range(option.rect.top(), option.rect.bottom() + 1)
    )
    assert any(
        image.pixelColor(x, y) == QColor("#103B38")
        for x in range(option.rect.left(), option.rect.right() + 1)
        for y in range(option.rect.top(), option.rect.bottom() + 1)
    )


def test_container_visibility_marks_private_only_when_every_page_is_private(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    container = {"id": "space-a", "name": "Manual", "metadata": {}}

    private_data = {
        "pages": [
            {"id": "p1", "_container_id": "space-a", "private": True},
            {"id": "p2", "_container_id": "space-a", "private": True},
        ]
    }
    mixed_data = {
        "pages": [
            {"id": "p1", "_container_id": "space-a", "private": True},
            {"id": "p2", "_container_id": "space-a", "public": True},
        ]
    }

    assert window._container_visibility(source, private_data, container) == ("Privada", "private")
    assert window._container_visibility(source, mixed_data, container) == ("Pública", "public")
    window.dirty = False


def test_public_auth_mode_marks_unannotated_container_as_public(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    source.auth_mode = AuthMode.PUBLIC
    container = {"id": "space-a", "name": "Manual", "metadata": {}}

    assert window._container_visibility(source, {}, container) == ("Pública", "public")
    window.dirty = False


def test_selection_browses_containers_without_losing_previous_choices(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    data = {
        "root": {"id": "all", "title": "Contêineres"},
        "pages": [
            {
                "id": "a1",
                "title": "Manual A",
                "_container_id": "space-a",
                "space": {"key": "space-a", "name": "Base de conhecimento"},
                "ancestors": [],
                "version": {"number": 1},
            },
            {
                "id": "b1",
                "title": "Manual B",
                "_container_id": "space-b",
                "space": {"key": "space-b", "name": "Marketing"},
                "ancestors": [],
                "version": {"number": 1},
            },
        ],
    }
    window.trees[source.id] = data
    window._populate_selection_tree(source, data)

    cards = {
        card.source_type: card
        for card in window.pages["selection"].findChildren(SourceCard)
    }
    assert set(cards) == {"space-a", "space-b"}

    window._open_selection_container("space-a")
    assert window.selection_stack.currentIndex() == 1
    leaf_a = window._leaf_items()[0]
    leaf_a.setCheckState(0, Qt.CheckState.Checked)
    assert window.selection_store.is_selected(source.id, "space-a", "a1")

    window._selection_go_back()
    window._open_selection_container("space-b")
    assert not window.selection_store.is_selected(source.id, "space-b", "b1")
    assert window.selection_store.is_selected(source.id, "space-a", "a1")
    window.dirty = False


def test_selection_orders_loaded_containers_first(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    window.trees[source.id] = {
        "root": {"id": "all", "title": "Contêineres"},
        "containers": [
            {"id": "space-a", "name": "A"},
            {"id": "space-b", "name": "B"},
            {"id": "space-c", "name": "C"},
        ],
        "pages_by_container": {
            "space-b": [{"id": "b1", "_container_id": "space-b"}],
            "space-a": [{"id": "a1", "_container_id": "space-a"}],
        },
    }

    containers = window._selection_containers(source)

    assert [item["id"] for item in containers] == ["space-b", "space-a", "space-c"]
    assert [item["loaded"] for item in containers] == [True, True, False]
    window.dirty = False


def test_space_search_filters_page_and_selection_cards(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    window._show_page("pages")
    window.show()
    source = window.project.sources[0]
    window.trees[source.id] = {
        "root": {"id": "all", "title": "Contêineres"},
        "containers": [
            {"id": "manual", "name": "Manual de operações"},
            {"id": "shopping", "name": "Shopping"},
            {"id": "manual-2", "name": "Manual financeiro"},
            {"id": "manual-3", "name": "Manual de suporte"},
        ],
        "pages_by_container": {},
    }

    window._refresh_pages_home()
    window.page_space_search.setText("manual")
    assert not window._page_container_cards["manual"].isHidden()
    assert window._page_container_cards["shopping"].isHidden()
    assert window.page_cards_layout.itemAtPosition(0, 0).widget() is window._page_container_cards["manual"]
    assert window.page_cards_layout.itemAtPosition(1, 0).widget() is window._page_container_cards["manual-2"]
    assert window.page_cards_layout.itemAtPosition(0, 1).widget() is window._page_container_cards["manual-3"]
    assert window.page_cards_scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded

    window.page_space_search.setText("shopping")
    shopping_card = window._page_container_cards["shopping"]
    assert shopping_card.isVisible()
    card_origin = shopping_card.mapTo(window.page_cards_scroll.viewport(), QPoint(0, 0))
    assert window.page_cards_scroll.viewport().rect().intersects(
        shopping_card.rect().translated(card_origin)
    )
    clicked: list[str] = []
    shopping_card.clicked.disconnect()
    shopping_card.clicked.connect(clicked.append)
    qtbot.mouseClick(shopping_card, Qt.MouseButton.LeftButton)
    assert clicked == ["shopping"]

    window._refresh_selection_home()
    window.selection_space_search.setText("shopping")
    assert window._selection_container_cards["manual"].isHidden()
    assert not window._selection_container_cards["shopping"].isHidden()
    window.dirty = False


def test_tree_cancel_buttons_follow_loading_state(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    window.show()
    window._show_page("pages")

    assert window.tree_cancel_button.isVisible()
    assert not window.tree_cancel_button.isEnabled()
    assert not window.selection_cancel_button.isEnabled()

    window._show_page("selection")
    assert window.selection_cancel_button.isVisible()

    window._set_tree_loading(True)
    assert window.tree_cancel_button.isEnabled()
    assert window.selection_cancel_button.isEnabled()

    window._set_tree_loading(False)
    assert not window.tree_cancel_button.isEnabled()
    assert not window.selection_cancel_button.isEnabled()
    window.dirty = False


def test_tree_cancel_is_immediate_without_confirmation(qtbot, monkeypatch) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    from alquimista.runtime import CancellationToken

    window.token = CancellationToken()
    window._set_tree_loading(True)
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: pytest.fail("cancelamento da árvore não deve perguntar"),
    )

    window._cancel_tree_operation()

    assert window.token.cancelled
    assert "Cancelamento solicitado" in window.tree_load_status.text()
    window._set_tree_loading(False)
    window.dirty = False


def test_worker_cancellation_resets_tree_ui_without_popup(qtbot, monkeypatch) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    from alquimista.runtime import CancellationToken

    window.token = CancellationToken()
    window.token.cancel()
    window._set_tree_loading(True)
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: pytest.fail("cancelamento não deve exibir popup crítico"),
    )

    window._worker_failed("Operação cancelada pelo usuário.", "")

    assert not window._tree_loading
    assert not window.tree_cancel_button.isEnabled()
    assert not window.selection_cancel_button.isEnabled()
    assert window.tree_load_status.text() == "Carregamento cancelado."
    window.dirty = False


def test_lazy_root_without_children_metadata_is_expandable(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    data = {
        "root": {"id": "all", "title": "Contêineres"},
        "containers": [{"id": "space-a", "name": "Base de conhecimento"}],
        "pages_by_container": {
            "space-a": [
                {
                    "id": "root-1",
                    "title": "Manual raiz",
                    "parent_id": None,
                    "_container_id": "space-a",
                }
            ]
        },
        "lazy_discovery": {
            "space-a": {"enabled": True, "loaded_parents": []}
        },
    }

    window._populate_page_tree_lazy(source, data, container_id="space-a")
    item = window.page_tree.topLevelItem(0)

    assert item is not None
    assert item.childCount() == 0
    assert (
        item.childIndicatorPolicy()
        == QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
    )
    window._populate_selection_tree(source, data, container_id="space-a")
    selection_item = window.selection_tree.topLevelItem(0)
    assert selection_item is not None
    assert (
        selection_item.childIndicatorPolicy()
        == QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
    )
    window.dirty = False


def test_lazy_tree_uses_ancestor_fallback_for_parent_attachment(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    data = {
        "root": {"id": "all", "title": "Contêineres"},
        "containers": [{"id": "space-a", "name": "Base de conhecimento"}],
        "pages_by_container": {
            "space-a": [
                {
                    "id": "child",
                    "title": "Página filha",
                    "ancestors": [{"id": "parent", "title": "Pasta pai"}],
                    "_container_id": "space-a",
                },
                {
                    "id": "parent",
                    "title": "Pasta pai",
                    "parent_id": None,
                    "_container_id": "space-a",
                },
            ]
        },
        "lazy_discovery": {
            "space-a": {"enabled": True, "loaded_parents": []}
        },
    }

    window._populate_page_tree_lazy(source, data, container_id="space-a")

    parent = window.page_tree.topLevelItem(0)
    assert parent is not None
    assert parent.text(0) == "Pasta pai"
    assert parent.childCount() == 1
    assert parent.child(0).text(0) == "Página filha"
    window.dirty = False


def test_select_all_loaded_pages_does_not_depend_on_render_limit(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    pages = [
        {"id": f"page-{index}", "_container_id": "space-a"}
        for index in range(1_200)
    ]
    window.trees[source.id] = {
        "root": {"id": "all", "title": "Contêineres"},
        "containers": [{"id": "space-a", "name": "A"}],
        "pages_by_container": {"space-a": pages},
    }
    window._populate_selection_tree(source, window.trees[source.id])

    window._set_selection(Qt.CheckState.Checked, visible_only=False)

    assert len(window.project.selected_keys_for(source.id)) == len(pages)
    assert len(source.selected_page_ids) == len(pages)
    window.dirty = False


def test_loaded_selection_is_scoped_to_active_container(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    data = {
        "root": {"id": "root", "title": "Manual"},
        "pages_by_container": {
            "space-a": [{"id": "page-a", "title": "A", "_container_id": "space-a"}],
            "space-b": [{"id": "page-b", "title": "B", "_container_id": "space-b"}],
        },
    }
    window.trees[source.id] = data
    window._active_selection_container = "space-a"
    window._populate_selection_tree(source, data, container_id="space-a")

    window._set_selection(Qt.CheckState.Checked, visible_only=False)

    assert window.selection_store.is_selected(source.id, "space-a", "page-a")
    assert not window.selection_store.is_selected(source.id, "space-b", "page-b")
    window.dirty = False


def test_ordered_pages_keeps_siblings_and_places_known_parents_first() -> None:
    pages = [
        {"id": "child-b", "parent_id": "parent"},
        {"id": "sibling"},
        {"id": "parent"},
        {"id": "child-a", "ancestors": [{"id": "parent"}]},
        {"id": "orphan", "parent_id": "missing"},
        {"id": "cycle-a", "parent_id": "cycle-b"},
        {"id": "cycle-b", "parent_id": "cycle-a"},
    ]

    assert [page["id"] for page in ordered_pages(pages)] == [
        "sibling",
        "parent",
        "child-b",
        "child-a",
        "orphan",
        "cycle-a",
        "cycle-b",
    ]


def test_ordered_pages_preserves_explicit_provider_order() -> None:
    pages = [
        {"id": "child", "parent_id": "parent", "provider_ordered": True},
        {"id": "parent", "provider_ordered": True},
    ]

    assert [page["id"] for page in ordered_pages(pages)] == ["child", "parent"]


def test_visible_selection_actions_do_not_change_hidden_loaded_pages(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    data = {
        "root": {"id": "root", "title": "Manual"},
        "pages": [
            {"id": "visible", "title": "Visible page", "_container_id": "space-a"},
            {"id": "hidden", "title": "Hidden page", "_container_id": "space-a"},
        ],
    }
    window.trees[source.id] = data
    window._populate_selection_tree(source, data)
    window.selection_search.setText("Visible")

    window._set_selection(Qt.CheckState.Checked, visible_only=True)
    assert source.selected_page_ids == ["visible"]

    window._set_selection(Qt.CheckState.Checked, visible_only=False)
    assert source.selected_page_ids == ["hidden", "visible"]
    window.dirty = False


def test_public_access_choice_and_accessible_column_movement(qtbot, monkeypatch) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    window.continue_without_login()
    source = window.source_by_combo(window.connection_source)
    assert source.auth_mode == AuthMode.PUBLIC
    assert "somente páginas públicas" in window.connection_state.text()

    logical = int(window.page_column_choice.currentData())
    before = window.page_tree.header().visualIndex(logical)
    window._move_page_column(1)
    assert window.page_tree.header().visualIndex(logical) == before + 1
    window._restore_table_columns(
        window.page_tree, [300, 90, 110, 180, 430, 80, 210], "pages"
    )
    assert window.page_tree.header().visualIndex(logical) == logical
    window.dirty = False


def test_output_and_review_pages(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    assert {"output", "review"}.issubset(window.pages)
    window._show_page("output")
    window.output_dir.setText("Base de conhecimento")
    assert "Estrutura prevista" in window.output_structure.text()
    assert window.project.extraction.pages_subdir in window.output_structure.text()
    assert window.project.consolidation.output_subdir in window.output_structure.text()
    window._show_page("review")
    assert "Modo de acesso" in window.review_summary.text()
    window.dirty = False


def test_single_flow_exposes_operation_choices(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    assert window.mode == "complete"
    assert window.execution_mode.itemData(0) == "complete"
    assert window.execution_mode.itemData(1) == "extract"
    assert window.execution_mode.itemData(2) == "consolidate"
    assert set(window.pages) >= {"extraction", "consolidation", "results"}
    window.execution_mode.setCurrentIndex(1)
    window._show_page("review")
    assert "Somente extrair" in window.review_summary.text()
    window.dirty = False


def test_consolidation_depth_control_round_trips(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    window.con_depth.setValue(2)
    window._sync_consolidation_controls()
    assert window.project.consolidation.module_depth == 2
    window.project.consolidation.module_depth = 1
    window._sync_consolidation_ui()
    assert window.con_depth.value() == 1
    window.dirty = False


def test_consolidation_depth_preview_changes_with_selected_level(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)

    window.con_depth_choice.setCurrentIndex(1)

    assert window.con_depth.value() == 2
    assert "2" in window.con_depth_example.text()
    assert "2" in window.con_depth_preview.text()
    window.dirty = False


def test_consolidation_preview_aggregates_groups_and_updates_metrics(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    window._render_consolidation_preview(
        [
            {"group": "Manual", "part": 1, "parts": 2, "pages": 4, "characters": 1200, "oversized": False},
            {"group": "Manual", "part": 2, "parts": 2, "pages": 3, "characters": 900, "oversized": False},
            {"group": "FAQ", "part": 1, "parts": 1, "pages": 2, "characters": 500, "oversized": True},
        ]
    )

    assert window.package_table.rowCount() == 2
    assert window.package_table.item(0, 1).text() == "Manual"
    assert window.package_table.item(0, 2).text() == "2"
    assert window.con_stat_labels["packages"].text() == "3"
    assert window.con_stat_labels["pages"].text() == "9"
    assert window.con_stat_labels["average"].text() == "3"
    assert "acima do limite" in window.con_preview_status.text()
    window.dirty = False


def test_selection_updates_source_without_blocking(qtbot) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    source = window.project.sources[0]
    data = {
        "root": {"id": "100", "title": "Manual"},
        "pages": [
            {
                "id": "10",
                "title": "Página",
                "ancestors": [{"id": "100", "title": "Manual"}],
                "version": {"number": 1},
            }
        ],
    }
    window._populate_selection_tree(source, data)
    leaf = window._leaf_items()[0]
    leaf.setCheckState(0, Qt.CheckState.Checked)
    assert source.selected_page_ids == ["10"]
    window.dirty = False


def test_failed_project_open_preserves_current_path_and_project(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{invalid", encoding="utf-8")
    original_project = window.project
    original_path = window.project_path
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        lambda *args, **kwargs: (str(invalid), ""),
    )
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)

    window.open_project()

    assert window.project is original_project
    assert window.project_path is original_path
    window.dirty = False


def test_invalid_source_edit_is_not_reported_as_saved(
    qtbot, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    window.project_path = tmp_path / "project.json"
    window.src_url.setText("not-a-url")
    window.mark_dirty()
    monkeypatch.setattr(QMessageBox, "critical", lambda *args, **kwargs: None)

    assert not window.save_project()

    assert window.dirty
    assert not window.project_path.exists()
    window.src_url.setText("https://example.test")
    window.dirty = False


def test_consolidation_preview_is_dispatched_to_worker(
    qtbot, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = MainWindow("complete")
    qtbot.addWidget(window)
    window.project.sources[0].selected_page_ids = ["page-1"]
    captured: dict[str, object] = {}

    def capture(function, done) -> None:
        captured["function"] = function
        captured["done"] = done

    monkeypatch.setattr(window, "_start_worker", capture)
    monkeypatch.setattr(window, "_validated_project_snapshot", lambda: window.project)
    window.preview_consolidation()

    assert callable(captured["function"])
    assert callable(captured["done"])
    window.dirty = False
