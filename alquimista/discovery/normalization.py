from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def normalize_web_url(url: str) -> str:
    cleaned = url.strip()
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    parsed = urlsplit(cleaned)
    return urlunsplit(
        (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", parsed.query, "")
    )


def is_url_in_scope(url: str, allowed_domains: set[str]) -> bool:
    try:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"}:
            return False
        host = parsed.hostname or ""
        return host in allowed_domains or any(host.endswith("." + d) for d in allowed_domains)
    except Exception:
        return False


__all__ = [
    "DEFAULT_USER_AGENT",
    "normalize_web_url",
    "is_url_in_scope",
]
