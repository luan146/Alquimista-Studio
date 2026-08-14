"""Pure helpers for source configuration and source selection.

This module deliberately has no Qt dependency. ``MainWindow`` remains the
owner of widgets and editing state; these helpers only transform or select
``SourceConfig`` values.
"""

from __future__ import annotations

from typing import Any, Protocol, Sequence

from ...models import SourceConfig
from ...source_detection import DetectedSource


class ComboDataProvider(Protocol):
    """Minimal combo-box contract needed by :func:`source_by_combo`."""

    def currentData(self) -> Any:  # noqa: N802 - mirrors the Qt API
        ...


def normalize_source_config(
    detected: DetectedSource,
    raw_url: str,
    name: str,
    previous: SourceConfig | None = None,
) -> SourceConfig:
    """Build a validated source from local URL-detection data.

    Existing identity, enablement, selection, and connector options are
    retained when editing a source. No credentials or network calls are
    introduced here; validation remains delegated to ``SourceConfig``.
    """

    options = dict(previous.connector_options) if previous else {}
    options.update({"source_url": raw_url, "detected_api": detected.api_name})
    updates: dict[str, Any] = {
        "name": name.strip() or detected.display_name,
        "source_type": detected.source_type,
        "base_url": detected.base_url,
        "space_key": detected.space_key,
        "space_name": detected.space_name,
        "root_mode": detected.root_mode,
        "root_value": detected.root_value,
        "connector_options": options,
    }
    if previous is not None:
        updates.update(
            {
                "id": previous.id,
                "enabled": previous.enabled,
                "include_root": previous.include_root,
                "selected_page_ids": list(previous.selected_page_ids),
                "consolidation_excluded_page_ids": list(
                    previous.consolidation_excluded_page_ids
                ),
            }
        )

    base = previous.model_dump() if previous else SourceConfig().model_dump()
    return SourceConfig.model_validate(base | updates)


def source_by_index(
    sources: Sequence[SourceConfig], index: int
) -> SourceConfig | None:
    """Return the source at ``index`` or ``None`` for an invalid row."""

    return sources[index] if 0 <= index < len(sources) else None


def source_by_identifier(
    sources: Sequence[SourceConfig], identifier: Any
) -> SourceConfig | None:
    """Return a source whose stable id matches ``identifier``."""

    if not identifier:
        return None
    return next((source for source in sources if source.id == identifier), None)


def source_by_combo(
    sources: Sequence[SourceConfig],
    combo: ComboDataProvider | None = None,
    *,
    fallback_index: int = -1,
) -> SourceConfig | None:
    """Resolve a source from combo data, preserving the UI fallback behavior."""

    if combo is not None and hasattr(combo, "currentData"):
        source = source_by_identifier(sources, combo.currentData())
        if source is not None:
            return source
    return source_by_index(sources, fallback_index)


def build_source_snapshot(source: SourceConfig) -> dict[str, Any]:
    """Return a JSON-compatible, detached snapshot of a source configuration."""

    return source.model_dump(mode="json", exclude={"state_file"})


def build_source_snapshots(
    sources: Sequence[SourceConfig],
) -> list[dict[str, Any]]:
    """Build detached snapshots for a sequence of sources."""

    return [build_source_snapshot(source) for source in sources]


__all__ = [
    "ComboDataProvider",
    "build_source_snapshot",
    "build_source_snapshots",
    "normalize_source_config",
    "source_by_combo",
    "source_by_identifier",
    "source_by_index",
]
