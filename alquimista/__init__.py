"""ALQuimista Studio application package."""

# Single source of the product version: build scripts, installer and User-Agent read it.
__version__ = "0.9.5"

from .models import (
    ConsolidationOptions,
    ExtractionOptions,
    MarkdownOptions,
    ProjectConfig,
    SourceConfig,
)

__all__ = [
    "ConsolidationOptions",
    "ExtractionOptions",
    "MarkdownOptions",
    "ProjectConfig",
    "SourceConfig",
]
