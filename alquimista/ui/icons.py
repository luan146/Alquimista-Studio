"""Interface icons: one SVG file per icon in assets/icons/ui (the user can replace any of them)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parents[2] / "assets" / "icons" / "ui"

# Index of the old 4x4 system atlas -> SVG name (button(), NAV_ICON_INDEX and page_header still pass indices).
SYSTEM_ICONS = (
    "inicio", "fontes", "conexao", "selecao", "markdown", "pacotes", "executar", "resultados",
    "configuracoes", "salvar", "adicionar", "pasta", "remover", "voltar", "pesquisar", "cancelar",
)
# Index of the old 4x2 auth atlas -> SVG name.
AUTH_ICONS = ("publico", "navegador", "usuario", "chave", "token", "protegido", "sessao", "sair")
# Emojis still stored in tree rows (ICON_ROLE) -> SVG name.
EMOJI_ICONS = {"\U0001f4c1": "pasta", "\U0001f4c2": "pasta", "\U0001f4c4": "pagina"}
# Check box and switch indicators referenced by the stylesheet.
CONTROL_ICONS = (
    "controle_check_off", "controle_check_on", "controle_check_partial",
    "controle_switch_off", "controle_switch_on", "controle_seta_baixo", "controle_seta_cima",
)


def icon_path(name: str) -> Path:
    return ICON_DIR / f"{name}.svg"


@lru_cache(maxsize=512)
def svg_pixmap(name: str, size: int, ratio: float = 2.0) -> QPixmap:
    """Render at size*ratio pixels so icons stay sharp at 125-150% interface scale."""
    renderer = QSvgRenderer(str(icon_path(name)))
    if not renderer.isValid():
        return QPixmap()
    pixels = max(1, round(size * ratio))
    pixmap = QPixmap(pixels, pixels)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRectF(0, 0, pixels, pixels))
    painter.end()
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def svg_icon(name: str, size: int = 24) -> QIcon:
    pixmap = svg_pixmap(name, size)
    return QIcon(pixmap) if not pixmap.isNull() else QIcon()
