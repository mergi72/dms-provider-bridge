from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
from collections.abc import Callable

import dms_provider_bridge.providers as providers_package
from dms_provider_bridge.core.config_loader import (
    connection_driver_name,
    list_connection_config_names,
    list_provider_config_names,
    load_config,
    load_connection_config,
)
from dms_provider_bridge.core.errors import ConfigurationError, ProviderNotFoundError
from dms_provider_bridge.providers.base import Provider


_PROVIDER_FACTORIES: dict[str, Callable[[], Provider]] | None = None
_PROVIDER_CACHE: dict[str, Provider] = {}


def _discover_provider_factories() -> dict[str, Callable[[], Provider]]:
    factories: dict[str, Callable[[], Provider]] = {}
    for module_info in pkgutil.iter_modules(providers_package.__path__):
        if module_info.name == "base":
            continue
        module = importlib.import_module(f"{providers_package.__name__}.{module_info.name}")
        for _name, candidate in inspect.getmembers(module, inspect.isclass):
            if candidate is Provider or not issubclass(candidate, Provider) or inspect.isabstract(candidate):
                continue
            provider_name = _normalize_provider_name(getattr(candidate, "name", None))
            if provider_name:
                factories[provider_name] = candidate
    return factories


def _provider_factories() -> dict[str, Callable[[], Provider]]:
    global _PROVIDER_FACTORIES
    if _PROVIDER_FACTORIES is None:
        _PROVIDER_FACTORIES = _discover_provider_factories()
    return _PROVIDER_FACTORIES


def _normalize_provider_name(provider_name: str | None) -> str | None:
    if provider_name is None:
        return None
    normalized = provider_name.strip().lower()
    if normalized.endswith(":"):
        normalized = normalized[:-1]
    return normalized or None


def _resolve_default_provider_name() -> str:
    """Return default provider name from config or DMS_PROVIDER_DEFAULT_PROVIDER."""
    registered = set(list_registered_providers())
    try:
        config = load_config()
        from_config = _normalize_provider_name(config.get("provider", {}).get("default"))
        if from_config and from_config in registered:
            return from_config
    except Exception:
        pass
    from_env = _normalize_provider_name(os.getenv("DMS_PROVIDER_DEFAULT_PROVIDER"))
    if from_env and from_env in registered:
        return from_env
    if registered:
        raise ConfigurationError(
            "Default provider is not configured. Set provider.default in bridge.json "
            "or DMS_PROVIDER_DEFAULT_PROVIDER."
        )
    raise ConfigurationError("No providers are registered.")


def get_provider(provider_name: str | None = None) -> Provider:
    name = _normalize_provider_name(provider_name) or _resolve_default_provider_name()
    registered = set(list_registered_providers())
    driver_name = connection_driver_name(name) or name
    factory = _provider_factories().get(driver_name)
    if name not in registered or factory is None:
        raise ProviderNotFoundError(f"Provider '{name}' is not registered.")
    provider = _PROVIDER_CACHE.get(name)
    if provider is None:
        config = load_connection_config(name) if connection_driver_name(name) else None
        try:
            provider = factory(name=name, config=config)
        except TypeError:
            provider = factory()
        _PROVIDER_CACHE[name] = provider
    return provider


def reload_provider_cache() -> None:
    """Clear provider instances so subsequent calls load fresh config."""
    _PROVIDER_CACHE.clear()


def list_registered_providers() -> list[str]:
    factories = _provider_factories()
    connections = [
        name for name in list_connection_config_names() if (connection_driver_name(name) or "") in factories
    ]
    if connections:
        return connections
    configured = [name for name in list_provider_config_names() if name in factories]
    if configured:
        return configured
    return sorted(factories.keys())


def get_default_provider_name() -> str:
    return _resolve_default_provider_name()

