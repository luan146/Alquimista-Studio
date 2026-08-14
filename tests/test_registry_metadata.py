from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from alquimista.connectors.registry import (
    ConnectorRegistry,
    default_registry,
)
from alquimista.models import ConnectorStatus
from alquimista.source_detection import detect_source_url
from alquimista.ui.components import SourceCard
from alquimista.ui.connector_forms import ConnectorFormSpec, form_spec
from alquimista.ui.pages.dashboard_page import _grid_position, build_dashboard_page


def test_default_registry_is_the_single_source_for_form_and_card_metadata() -> None:
    registry = default_registry()
    descriptors = registry.all()

    assert {item.source_type for item in descriptors} == {
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

    assert len({item.card.order for item in descriptors}) == len(descriptors)
    for descriptor in descriptors:
        assert descriptor.form is form_spec(descriptor)
        assert descriptor.form == form_spec(descriptor.source_type, registry)
        assert descriptor.card.visible is True
        assert descriptor.card.description

    assert form_spec("unknown", ConnectorRegistry()) == ConnectorFormSpec()


def test_runnable_requires_operational_status_implementation_and_factory() -> None:
    descriptor = default_registry().get("confluence_rest")

    assert descriptor.runnable is True
    assert replace(descriptor, status=ConnectorStatus.DEVELOPMENT).runnable is False
    assert replace(descriptor, implemented=False).runnable is False
    assert replace(descriptor, factory=None).runnable is False


def test_confluence_lazy_discovery_is_declared_by_descriptor_and_runtime() -> None:
    descriptor = default_registry().get("confluence_rest")
    connector = descriptor.factory.__new__(descriptor.factory)  # type: ignore[union-attr]

    assert descriptor.capabilities.supports_lazy_discovery is True
    assert connector.get_capabilities().supports_lazy_discovery is True
    assert default_registry().get("notion_api").capabilities.supports_lazy_discovery is True


def test_detection_uses_registry_names_without_changing_url_parsing() -> None:
    original = default_registry().get("confluence_rest")
    registry = ConnectorRegistry(
        [
            replace(
                original,
                display_name="Wiki corporativa",
                integration_name="API canônica",
            )
        ]
    )

    detected = detect_source_url(
        "https://docs.example.com/display/DOC/Manual+interno",
        registry,
    )

    assert detected.display_name == "Wiki corporativa"
    assert detected.api_name == "API canônica"
    assert detected.base_url == "https://docs.example.com"
    assert detected.space_key == "DOC"
    assert detected.root_value == "Manual interno"


@pytest.mark.parametrize(
    ("index", "total", "expected"),
    [
        (0, 5, (0, 0, 2)),
        (1, 5, (0, 2, 2)),
        (2, 5, (0, 4, 2)),
        (3, 5, (1, 1, 2)),
        (4, 5, (1, 3, 2)),
        (0, 2, (0, 1, 2)),
        (1, 2, (0, 3, 2)),
    ],
)
def test_dashboard_grid_centers_incomplete_rows(
    index: int, total: int, expected: tuple[int, int, int]
) -> None:
    assert _grid_position(index, total) == expected


def test_dashboard_cards_are_created_from_registry_order(qtbot) -> None:
    registry = default_registry()
    descriptors = [
        replace(registry.get("gitbook_api"), card=replace(registry.get("gitbook_api").card, order=0)),
        replace(registry.get("confluence_rest"), card=replace(registry.get("confluence_rest").card, order=1)),
    ]
    window = SimpleNamespace(
        connector_registry=ConnectorRegistry(descriptors),
        _source_card_clicked=lambda _source_type: None,
    )

    page = build_dashboard_page(window)
    qtbot.addWidget(page)
    cards = page.findChildren(SourceCard)

    assert [card.source_type for card in cards] == ["gitbook_api", "confluence_rest"]
