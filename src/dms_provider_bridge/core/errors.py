class BridgeError(Exception):
    """Base exception for dms-provider-bridge."""


class ProviderNotFoundError(BridgeError):
    """Raised when provider cannot be resolved."""


class ConfigurationError(BridgeError):
    """Raised when bridge configuration is invalid or incomplete."""


class ProviderOperationError(BridgeError):
    """Raised when provider operation fails."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class AuthenticationError(BridgeError):
    """Raised when provider authentication context is invalid."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class VersionRequiredError(ProviderOperationError):
    """Raised when an existing DMS document requires explicit version choice."""

    def __init__(self, message: str, metadata: dict | None = None) -> None:
        super().__init__(message)
        self.metadata = metadata or {}
