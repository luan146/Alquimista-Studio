from __future__ import annotations

from typing import Any


class NotionDocumentParser:
    """Deterministic conversion of Notion blocks to canonical Markdown."""

    def __init__(self, *, max_depth: int = 50, max_blocks: int = 10_000) -> None:
        self.max_depth = max_depth
        self.max_blocks = max_blocks

    @staticmethod
    def _text(items: Any) -> str:
        out: list[str] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            text_obj = item.get("text")
            if not isinstance(text_obj, dict):
                text_obj = {}
            value = str(item.get("plain_text") or text_obj.get("content") or "")
            annotations = item.get("annotations")
            if not isinstance(annotations, dict):
                annotations = {}
            if annotations.get("code"):
                value = f"`{value}`"
            if annotations.get("bold"):
                value = f"**{value}**"
            if annotations.get("italic"):
                value = f"*{value}*"
            if annotations.get("strikethrough"):
                value = f"~~{value}~~"
            href = item.get("href") or text_obj.get("link")
            if isinstance(href, dict):
                href = href.get("url")
            if href:
                value = f"[{value}]({href})"
            out.append(value)
        return "".join(out)

    def render(self, blocks: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for block in blocks:
            self._render_block(block, lines, 0)
        return "\n\n".join(line for line in lines if line is not None).strip()

    def _render_block(self, block: dict[str, Any], lines: list[str], depth: int) -> None:
        if depth > self.max_depth:
            raise ValueError("A árvore de blocos do Notion excedeu a profundidade máxima.")
        btype = str(block.get("type") or "unsupported")
        data = block.get(btype)
        if not isinstance(data, dict):
            data = {}
        text = self._text(data.get("rich_text"))
        indent = "  " * max(depth - 1, 0)

        if btype == "paragraph":
            line = f"{indent}{text}" if text else ""
        elif btype.startswith("heading_"):
            try:
                level = min(max(int(btype.split("_")[-1]), 1), 6)
            except ValueError:
                level = 2
            line = f"{'#' * level} {text}"
        elif btype == "bulleted_list_item":
            line = f"{indent}- {text}"
        elif btype == "numbered_list_item":
            line = f"{indent}1. {text}"
        elif btype == "to_do":
            checked = "x" if data.get("checked") else " "
            line = f"{indent}- [{checked}] {text}"
        elif btype == "quote":
            line = f"> {text}"
        elif btype == "callout":
            icon_obj = data.get("icon") or {}
            emoji = icon_obj.get("emoji", "")
            prefix = f"{emoji} " if emoji else "💡 "
            line = f"> {prefix}{text}"
        elif btype == "toggle":
            child_lines: list[str] = []
            for child in block.get("_children", []) or []:
                if isinstance(child, dict):
                    self._render_block(child, child_lines, depth + 1)
            inner = "\n\n".join(cl for cl in child_lines if cl).strip()
            line = f"<details>\n<summary>{text or 'Detalhes'}</summary>\n\n{inner}\n</details>" if inner else f"<details>\n<summary>{text or 'Detalhes'}</summary>\n</details>"
            lines.append(line)
            return
        elif btype == "code":
            lang = data.get("language") or ""
            line = f"```{lang}\n{text}\n```"
        elif btype == "equation":
            expr = data.get("expression") or text
            line = f"$${expr}$$"
        elif btype == "divider":
            line = "---"
        elif btype == "image":
            file_obj = data.get("file") or data.get("external") or {}
            img_url = str(file_obj.get("url") or "")
            caption = self._text(data.get("caption")) or "Imagem"
            line = f"![{caption}]({img_url})" if img_url else ""
        elif btype == "bookmark":
            url = data.get("url") or ""
            caption = self._text(data.get("caption")) or url or "Bookmark"
            line = f"[{caption}]({url})" if url else ""
        elif btype == "embed":
            url = data.get("url") or ""
            line = f"[Embed]({url})" if url else ""
        elif btype == "child_page":
            line = f"## {data.get('title') or 'Página filha'}"
        elif btype == "table":
            # Bloco contêiner de tabela: renderiza linhas filhas
            rows = block.get("_children", [])
            table_lines: list[str] = []
            has_header = data.get("has_column_header", True)
            for idx, r in enumerate(rows):
                if isinstance(r, dict):
                    r_data = r.get("table_row", {})
                    cells = [self._text(c) for c in r_data.get("cells", [])]
                    table_lines.append(f"| {' | '.join(cells)} |")
                    if idx == 0 and has_header and cells:
                        table_lines.append(f"| {' | '.join(['---'] * len(cells))} |")
            line = "\n".join(table_lines)
            lines.append(line)
            return
        elif btype == "table_row":
            cells = [self._text(c) for c in data.get("cells", [])]
            line = f"| {' | '.join(cells)} |" if cells else ""
        elif btype in {"column_list", "column", "synced_block"}:
            line = ""
        elif btype == "link_to_page":
            page_id = data.get("page_id") or data.get("database_id") or ""
            line = f"[Página #{page_id}](notion://{page_id})" if page_id else ""
        else:
            line = f"<!-- unsupported:notion:{btype} -->"

        if line:
            lines.append(line)

        for child in block.get("_children", []) or []:
            if isinstance(child, dict):
                self._render_block(child, lines, depth + 1)

