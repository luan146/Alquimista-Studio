from __future__ import annotations

from ..connectors.registry import (
    ConnectorDescriptor,
    ConnectorFormSpec,
    ConnectorRegistry,
    default_registry,
)


def form_spec(
    connector: str | ConnectorDescriptor,
    registry: ConnectorRegistry | None = None,
) -> ConnectorFormSpec:
    """Compatibility facade backed exclusively by connector descriptors."""

    if isinstance(connector, ConnectorDescriptor):
        return connector.form
    try:
        return (registry or default_registry()).get(connector).form
    except ValueError:
        return ConnectorFormSpec()


__all__ = ["ConnectorFormSpec", "form_spec"]
