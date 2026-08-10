"""Typed application errors presented safely by the GUI."""


class AlquimistaError(RuntimeError):
    """Base class for expected functional errors."""


class AuthenticationError(AlquimistaError):
    pass


class PermissionDeniedError(AlquimistaError):
    pass


class ResourceNotFoundError(AlquimistaError):
    pass


class ConfluenceConnectionError(AlquimistaError):
    pass


class ApiConnectionError(AlquimistaError):
    """A reusable connector HTTP client could not complete a request."""


class ApiRateLimitError(ApiConnectionError):
    pass


class RateLimitError(ConfluenceConnectionError):
    pass


class InvalidResponseError(ConfluenceConnectionError):
    pass


class InvalidProjectError(AlquimistaError):
    pass


class ManifestError(AlquimistaError):
    pass


class StorageError(AlquimistaError):
    pass


class ExtractionCancelledError(AlquimistaError):
    pass
