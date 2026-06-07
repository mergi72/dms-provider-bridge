from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
from collections.abc import Callable

import dms_provider_bridge.providers as providers_package
from dms_provider_bridge.core.config_loader import list_provider_config_names, load_config
from dms_provider_bridge.core.errors import ProviderNotFoundError
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
    """Return default provider name from config, then env var, then built-in fallback."""
    registered = set(list_registered_providers())
    try:
        config = load_config()
        from_config = _normalize_provider_name(config.get("provider", {}).get("default"))
        if from_config and from_config in registered:
            return from_config
    except Exception:
        pass
    from_env = _normalize_provider_name(os.getenv("EDOCAT_PROVIDER"))
    if from_env and from_env in registered:
        return from_env
    if "edocat" in registered:
        return "edocat"
    if registered:
        return sorted(registered)[0]
    return "edocat"


def get_provider(provider_name: str | None = None) -> Provider:
    name = _normalize_provider_name(provider_name) or _resolve_default_provider_name()
    registered = set(list_registered_providers())
    factory = _provider_factories().get(name)
    if name not in registered or factory is None:
        raise ProviderNotFoundError(f"Provider '{name}' is not registered.")
    provider = _PROVIDER_CACHE.get(name)
    if provider is None:
        provider = factory()
        _PROVIDER_CACHE[name] = provider
    return provider


def list_registered_providers() -> list[str]:
    factories = _provider_factories()
    configured = [name for name in list_provider_config_names() if name in factories]
    if configured:
        return configured
    return sorted(factories.keys())


def get_default_provider_name() -> str:
    return _resolve_default_provider_name()

