class BridgeError(Exception):
    """Base exception for dms-provider-bridge."""


class ConnectionNotFoundError(BridgeError):
    """Raised when connection cannot be resolved."""


# Backward-compatible alias for older provider-named call sites.
ProviderNotFoundError = ConnectionNotFoundError


class ConfigurationError(BridgeError):
    """Raised when bridge configuration is invalid or incomplete."""


class ConnectionOperationError(BridgeError):
    """Raised when a connection operation fails."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# Backward-compatible alias for older provider-named call sites.
ProviderOperationError = ConnectionOperationError


class AuthenticationError(BridgeError):
    """Raised when provider authentication context is invalid."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class VersionRequiredError(ConnectionOperationError):
    """Raised when an existing DMS document requires explicit version choice."""

    def __init__(self, message: str, metadata: dict | None = None) -> None:
        super().__init__(message)
        self.metadata = metadata or {}
