from __future__ import annotations

from .crawler import WebCrawler
from .frameworks import FRAMEWORK_SIGNATURES, detect_documentation_framework
from .llms_txt import probe_llms_txt
from .models import DiscoveredResource, DiscoveryResult, DiscoveryStrategy
from .normalization import DEFAULT_USER_AGENT, is_url_in_scope, normalize_web_url
from .service import SourceDiscoveryService
from .sitemap import probe_sitemap

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
