from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime


def normalize_markdown(text: str) -> str:
    value = unicodedata.normalize("NFC", text or "")
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = "\n".join(line.rstrip() for line in value.splitlines())
    return re.sub(r"\n{3,}", "\n\n", value).strip()


def format_updated_at(value: str | None) -> str:
    """Format Confluence timestamps as DD/MM/YYYY HH:MM."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return str(value)


def sha256_text(text: str) -> str:
    return hashlib.sha256(normalize_markdown(text).encode("utf-8")).hexdigest()


__all__ = ["format_updated_at", "normalize_markdown", "sha256_text"]
