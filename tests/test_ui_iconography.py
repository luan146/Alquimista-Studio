from __future__ import annotations

from pathlib import Path

from alquimista.connectors.registry import default_registry
from alquimista.ui.components import AlchemistIconAtlas
from alquimista.ui.main_window import MainWindow


def test_generated_icon_atlases_and_connector_metadata_are_complete() -> None:
    root = Path(__file__).resolve().parents[1]
    for filename in (
        "alchemist_system_atlas.png",
        "alchemist_connector_atlas.png",
        "alchemist_auth_atlas.png",
    ):
        asset = root / "assets" / "icons" / filename
        assert asset.exists()
        assert asset.stat().st_size > 1000

    descriptors = [item for item in default_registry().all() if item.card.visible]
    icon_indexes = [item.card.icon for item in descriptors]
    assert len(descriptors) == 28
    assert len(set(icon_indexes)) == 28
    assert set(icon_indexes) == set(range(28))


def test_all_system_connector_and_auth_icons_load(qtbot) -> None:
    assert all(not AlchemistIconAtlas.icon(index, 20).isNull() for index in range(16))
    assert all(
        not AlchemistIconAtlas.connector_icon(index, 24).isNull()
        for index in range(28)
    )
    assert all(
        not AlchemistIconAtlas.auth_icon(index, 24).isNull() for index in range(8)
    )

    window = MainWindow()
    qtbot.addWidget(window)
    assert all(
        not window.auth_mode.itemIcon(index).isNull()
        for index in range(window.auth_mode.count())
    )
