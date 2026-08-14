from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..source_detection import DetectedSource


class DiscoveryStrategy(StrEnum):
    OFFICIAL_API = "official_api"
    LLMS_TXT = "llms_txt"
    SITEMAP = "sitemap"
    HTML_CRAWLER = "html_crawler"
    SINGLE_PAGE = "single_page"


@dataclass
class DiscoveredResource:
    url: str
    title: str = ""
    resource_type: str = "page"  # "page", "llms_txt", "sitemap", "api"
    parent_url: str | None = None
    depth: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryResult:
    strategy: DiscoveryStrategy
    detected_source: DetectedSource
    resources: list[DiscoveredResource] = field(default_factory=list)
    llms_txt_url: str | None = None
    sitemap_url: str | None = None
    framework: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)


__all__ = [
    "DiscoveryStrategy",
    "DiscoveredResource",
    "DiscoveryResult",
]
