"""Compatibility facade for alquimista.discovery.

New code should import from :mod:`alquimista.discovery`.
"""
from __future__ import annotations

from .discovery import (
    DEFAULT_USER_AGENT,
    FRAMEWORK_SIGNATURES,
    DiscoveredResource,
    DiscoveryResult,
    DiscoveryStrategy,
    SourceDiscoveryService,
    WebCrawler,
    detect_documentation_framework,
    is_url_in_scope,
    normalize_web_url,
    probe_llms_txt,
    probe_sitemap,
)

__all__ = [
    "DEFAULT_USER_AGENT",
    "DiscoveredResource",
    "DiscoveryResult",
    "DiscoveryStrategy",
    "FRAMEWORK_SIGNATURES",
    "SourceDiscoveryService",
    "WebCrawler",
    "detect_documentation_framework",
    "is_url_in_scope",
    "normalize_web_url",
    "probe_llms_txt",
    "probe_sitemap",
]
