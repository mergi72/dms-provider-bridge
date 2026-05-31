class BridgeError(Exception):
    """Base exception for edocat-bridge."""


class ProviderNotFoundError(BridgeError):
    """Raised when provider cannot be resolved."""


class ProviderOperationError(BridgeError):
    """Raised when provider operation fails."""


class AuthenticationError(BridgeError):
    """Raised when provider authentication context is invalid."""
