"""Compatibility facade for ALQuimista Studio 5.

New code should import from :mod:`alquimista`.
"""

from alquimista.client import ConfluenceClient
from alquimista.errors import *
from alquimista.markdown import (
    MarkdownTransformer,
    normalize_markdown,
    page_metadata,
    relative_ancestor_titles,
    sha256_text,
)
from alquimista.models import (
    SCHEMA_VERSION,
    ConsolidationOptions,
    ExtractionOptions,
    ManifestDocument,
    ManifestEntry,
    MarkdownOptions,
    ProjectConfig,
    SourceConfig,
    default_project,
    now_iso,
    slugify,
    stable_json_hash,
)
from alquimista.runtime import CancellationToken
from alquimista.services import (
    ConsolidationService,
    ExtractionService,
    SourceRuntime,
    demote_headings,
    sanitize_filename,
)
from alquimista.storage import (
    FAILURES_NAME,
    MANIFEST_NAME,
    PACKAGE_INDEX_NAME,
    REPORT_NAME,
    ManifestStore,
    atomic_write_json,
    atomic_write_text,
    load_json,
    load_project,
    save_project,
)

# Historical names kept for local integrations.
MultiSourceExtractor = ExtractionService
Consolidator = ConsolidationService


def clone_project(project: ProjectConfig) -> ProjectConfig:
    return project.model_copy(deep=True)


__all__ = [
    "ConfluenceClient",
    "MarkdownTransformer",
    "normalize_markdown",
    "page_metadata",
    "relative_ancestor_titles",
    "sha256_text",
    "SCHEMA_VERSION",
    "ConsolidationOptions",
    "ExtractionOptions",
    "ManifestDocument",
    "ManifestEntry",
    "MarkdownOptions",
    "ProjectConfig",
    "SourceConfig",
    "default_project",
    "now_iso",
    "slugify",
    "stable_json_hash",
    "CancellationToken",
    "ConsolidationService",
    "ExtractionService",
    "SourceRuntime",
    "demote_headings",
    "sanitize_filename",
    "FAILURES_NAME",
    "MANIFEST_NAME",
    "PACKAGE_INDEX_NAME",
    "REPORT_NAME",
    "ManifestStore",
    "atomic_write_json",
    "atomic_write_text",
    "load_json",
    "load_project",
    "save_project",
    "MultiSourceExtractor",
    "Consolidator",
    "clone_project",
]
