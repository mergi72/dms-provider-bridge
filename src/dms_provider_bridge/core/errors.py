class BridgeError(Exception):
    """Base exception for dms-provider-bridge."""


class ProviderNotFoundError(BridgeError):
    """Raised when provider cannot be resolved."""


class ConfigurationError(BridgeError):
    """Raised when bridge configuration is invalid or incomplete."""


class ProviderOperationError(BridgeError):
    """Raised when provider operation fails."""


class AuthenticationError(BridgeError):
    """Raised when provider authentication context is invalid."""
