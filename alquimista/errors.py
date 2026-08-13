"""Typed application errors presented safely by the GUI."""


class AlquimistaError(RuntimeError):
    """Base class for expected functional errors."""


class ConnectorError(AlquimistaError):
    """Base class for expected connector and remote-source failures."""


class AuthenticationError(ConnectorError):
    pass


class PermissionDeniedError(ConnectorError):
    pass


class ResourceNotFoundError(ConnectorError):
    pass


class ApiConnectionError(ConnectorError):
    """A reusable connector HTTP client could not complete a request."""


class ApiRateLimitError(ApiConnectionError):
    pass


class InvalidResponseError(ApiConnectionError):
    pass


# Public compatibility names retained for callers that still use the former
# Confluence-specific transport hierarchy.
ConfluenceConnectionError = ApiConnectionError
RateLimitError = ApiRateLimitError


class InvalidProjectError(AlquimistaError):
    pass


class ManifestError(AlquimistaError):
    pass


class StorageError(AlquimistaError):
    pass


class ExtractionCancelledError(AlquimistaError):
    pass
