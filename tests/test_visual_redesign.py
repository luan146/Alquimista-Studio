"""Novo visual: ícones SVG, tema, peças novas e telas remontadas."""
from __future__ import annotations

from alquimista.ui.components import AlchemistIconAtlas
from alquimista.ui.icons import AUTH_ICONS, CONTROL_ICONS, EMOJI_ICONS, SYSTEM_ICONS, icon_path, svg_pixmap


def test_every_mapped_icon_has_an_svg_that_renders(qapp) -> None:
    names = {*SYSTEM_ICONS, *AUTH_ICONS, *EMOJI_ICONS.values(), "pagina_restrita", *CONTROL_ICONS}
    for name in names:
        assert icon_path(name).exists(), name
        assert not svg_pixmap(name, 24).isNull(), name


def test_old_atlas_indices_now_draw_the_svg_icons(qapp) -> None:
    assert AlchemistIconAtlas.pixmap(11, 32).cacheKey() == svg_pixmap("pasta", 32).cacheKey()
    assert AlchemistIconAtlas.auth_pixmap(7, 24).cacheKey() == svg_pixmap("sair", 24).cacheKey()
    assert not AlchemistIconAtlas.connector_icon(0, 24).isNull()  # plataformas continuam no atlas
