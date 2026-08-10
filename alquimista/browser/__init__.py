"""Lazy discovery contracts, cache, and service."""

from .cache import BrowserCache
from .contracts import (
    CancellationLike,
    DiscoveryAdapter,
    DiscoveryPage,
    DocumentMetadata,
    PageRequest,
    SearchResult,
    SpaceMetadata,
    Visibility,
)
from .service import CacheMissError, LazyDiscoveryService

__all__ = [
    "BrowserCache",
    "CacheMissError",
    "CancellationLike",
    "DiscoveryAdapter",
    "DiscoveryPage",
    "DocumentMetadata",
    "LazyDiscoveryService",
    "PageRequest",
    "SearchResult",
    "SpaceMetadata",
    "Visibility",
]
