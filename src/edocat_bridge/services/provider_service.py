from __future__ import annotations

import os

from edocat_bridge.core.errors import ProviderNotFoundError
from edocat_bridge.providers.alfresco import AlfrescoProvider
from edocat_bridge.providers.base import Provider
from edocat_bridge.providers.edocat import EdocatProvider
from edocat_bridge.providers.fso import FsoProvider


_PROVIDER_REGISTRY: dict[str, Provider] = {
    "edocat": EdocatProvider(),
    "alfresco": AlfrescoProvider(),
    "fso": FsoProvider(),
}


def _normalize_provider_name(provider_name: str | None) -> str | None:
    if provider_name is None:
        return None
    normalized = provider_name.strip().lower()
    if normalized.endswith(":"):
        normalized = normalized[:-1]
    return normalized or None


def get_provider(provider_name: str | None = None) -> Provider:
    name = _normalize_provider_name(provider_name) or _normalize_provider_name(os.getenv("EDOCAT_PROVIDER")) or "edocat"
    provider = _PROVIDER_REGISTRY.get(name)
    if provider is None:
        raise ProviderNotFoundError(f"Provider '{name}' is not registered.")
    return provider


def list_registered_providers() -> list[str]:
    return sorted(_PROVIDER_REGISTRY.keys())


def get_default_provider_name() -> str:
    configured = _normalize_provider_name(os.getenv("EDOCAT_PROVIDER"))
    if configured and configured in _PROVIDER_REGISTRY:
        return configured
    return "edocat"
