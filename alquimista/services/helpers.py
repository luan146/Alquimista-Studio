from __future__ import annotations

import re


def sanitize_filename(value: str, maximum: int = 120) -> str:
    result = re.sub(r'[\\/*?:"<>|\x00-\x1f]', "", value or "").strip()
    result = re.sub(r"\s+", "_", result).strip(" ._")
    reserved = {
        "con",
        "prn",
        "aux",
        "nul",
        *(f"com{n}" for n in range(1, 10)),
        *(f"lpt{n}" for n in range(1, 10)),
    }
    if result.casefold() in reserved:
        result = f"_{result}"
    return (result or "sem_titulo")[:maximum]


def demote_headings(markdown: str, levels: int) -> str:
    if levels <= 0:
        return markdown
    return re.sub(
        r"^(#{1,6})\s+(.+)$",
        lambda match: f"{'#' * min(6, len(match.group(1)) + levels)} {match.group(2)}",
        markdown,
        flags=re.MULTILINE,
    )


__all__ = ["sanitize_filename", "demote_headings"]
