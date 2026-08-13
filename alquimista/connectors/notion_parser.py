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
        if btype == "paragraph": line = f"{indent}{text}"
        elif btype.startswith("heading_"): line = f"{'#' * int(btype[-1])} {text}"
        elif btype == "bulleted_list_item": line = f"{indent}- {text}"
        elif btype == "numbered_list_item": line = f"{indent}1. {text}"
        elif btype == "to_do": line = f"{indent}- [{'x' if data.get('checked') else ' '}] {text}"
        elif btype in {"quote", "callout"}: line = f"> {text}"
        elif btype == "toggle": line = f"<details>\n<summary>{text}</summary>\n</details>"
        elif btype == "code": line = f"```{data.get('language') or ''}\n{text}\n```"
        elif btype == "equation": line = f"$${data.get('expression') or ''}$$"
        elif btype == "divider": line = "---"
        elif btype == "bookmark": line = f"[{data.get('caption') or data.get('url') or 'Bookmark'}]({data.get('url') or ''})"
        elif btype == "embed": line = f"[Embed]({data.get('url') or ''})"
        elif btype == "child_page": line = f"## {data.get('title') or 'Página filha'}"
        elif btype == "table_row": line = " | ".join(self._text(cell) for cell in data.get("cells", []))
        elif btype == "table": line = ""
        else:
            line = f"<!-- unsupported:notion:{btype} -->"
        lines.append(line)
        for child in block.get("_children", []) or []:
            if isinstance(child, dict):
                self._render_block(child, lines, depth + 1)
