from __future__ import annotations

import os

from dms_provider_bridge.core.config_loader import load_config
from dms_provider_bridge.core.errors import ProviderNotFoundError
from dms_provider_bridge.providers.alfresco import AlfrescoProvider
from dms_provider_bridge.providers.base import Provider
from dms_provider_bridge.providers.edocat import EdocatProvider
from dms_provider_bridge.providers.fso import FsoProvider


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


def _resolve_default_provider_name() -> str:
    """Return default provider name from config, then env var, then built-in fallback."""
    try:
        config = load_config()
        from_config = _normalize_provider_name(config.get("provider", {}).get("default"))
        if from_config and from_config in _PROVIDER_REGISTRY:
            return from_config
    except Exception:
        pass
    from_env = _normalize_provider_name(os.getenv("EDOCAT_PROVIDER"))
    if from_env and from_env in _PROVIDER_REGISTRY:
        return from_env
    return "edocat"


def get_provider(provider_name: str | None = None) -> Provider:
    name = _normalize_provider_name(provider_name) or _resolve_default_provider_name()
    provider = _PROVIDER_REGISTRY.get(name)
    if provider is None:
        raise ProviderNotFoundError(f"Provider '{name}' is not registered.")
    return provider


def list_registered_providers() -> list[str]:
    return sorted(_PROVIDER_REGISTRY.keys())


def get_default_provider_name() -> str:
    return _resolve_default_provider_name()

