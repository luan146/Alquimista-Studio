from __future__ import annotations

from collections.abc import Callable
from typing import Any


def sample_page(translator: Callable[[str], str] | None = None) -> dict[str, Any]:
    translate = translator or (lambda value: value)
    return {
        "id": "123456",
        "title": translate("Como configurar uma venda"),
        "ancestors": [
            {"id": "100", "title": translate("Manual do Produto")},
            {"id": "110", "title": "POS"},
        ],
        "space": {"key": "EXEMPLO", "name": translate("Espaço de exemplo")},
        "version": {
            "number": 4,
            "when": "2026-07-26T15:00:00Z",
            "by": {"displayName": translate("Equipe de Produto")},
        },
        "metadata": {"labels": {"results": [{"name": translate("vendas")}]}},
        "body": {
            "storage": {
                "value": (
                    f"<p>{translate('Este é um exemplo de conteúdo técnico.')}</p>"
                    "<ac:structured-macro ac:name='tip'><ac:rich-text-body>"
                    f"<p>{translate('Revise os dados antes de concluir.')}</p>"
                    "</ac:rich-text-body></ac:structured-macro>"
                )
            }
        },
        "_links": {"webui": "/pages/viewpage.action?pageId=123456"},
    }


__all__ = ["sample_page"]
