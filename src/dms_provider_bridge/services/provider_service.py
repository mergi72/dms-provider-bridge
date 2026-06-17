from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
from collections.abc import Callable

import dms_provider_bridge.providers as providers_package
from dms_provider_bridge.core.config_loader import (
    connection_driver_name,
    load_connection_metadata,
    list_connection_config_names,
    list_provider_config_names,
    load_config,
    load_connection_config,
)
from dms_provider_bridge.core.errors import ConfigurationError, ProviderNotFoundError
from dms_provider_bridge.providers.base import Provider


_DRIVER_FACTORIES: dict[str, Callable[[], Provider]] | None = None
_PROVIDER_CACHE: dict[str, Provider] = {}


def _discover_driver_factories() -> dict[str, Callable[[], Provider]]:
    factories: dict[str, Callable[[], Provider]] = {}
    for module_info in pkgutil.iter_modules(providers_package.__path__):
        if module_info.name == "base":
            continue
        module = importlib.import_module(f"{providers_package.__name__}.{module_info.name}")
        for _name, candidate in inspect.getmembers(module, inspect.isclass):
            if candidate is Provider or not issubclass(candidate, Provider) or inspect.isabstract(candidate):
                continue
            driver_name = _normalize_driver_name(getattr(candidate, "name", None))
            if driver_name:
                factories[driver_name] = candidate
    return factories


def _driver_factories() -> dict[str, Callable[[], Provider]]:
    global _DRIVER_FACTORIES
    if _DRIVER_FACTORIES is None:
        _DRIVER_FACTORIES = _discover_driver_factories()
    return _DRIVER_FACTORIES


def _discover_provider_factories() -> dict[str, Callable[[], Provider]]:
    """Compatibility alias for the old provider-factory name."""
    return _discover_driver_factories()


def _provider_factories() -> dict[str, Callable[[], Provider]]:
    """Compatibility alias for the old provider-factory registry."""
    return _driver_factories()


def _normalize_connection_name(connection_name: str | None) -> str | None:
    if connection_name is None:
        return None
    normalized = connection_name.strip().lower()
    if normalized.endswith(":"):
        normalized = normalized[:-1]
    return normalized or None


def _normalize_driver_name(driver_name: str | None) -> str | None:
    return _normalize_connection_name(driver_name)


def _normalize_provider_name(provider_name: str | None) -> str | None:
    return _normalize_connection_name(provider_name)


def _resolve_default_connection_name() -> str:
    """Return default connection name from config or legacy provider env/config."""
    registered = set(list_registered_connections())
    try:
        config = load_config()
        from_config = _normalize_connection_name(config.get("provider", {}).get("default"))
        if from_config and from_config in registered:
            return from_config
    except Exception:
        pass
    from_env = _normalize_connection_name(os.getenv("DMS_PROVIDER_DEFAULT_PROVIDER"))
    if from_env and from_env in registered:
        return from_env
    if registered:
        raise ConfigurationError(
            "Default connection is not configured. Set provider.default in bridge.json "
            "or DMS_PROVIDER_DEFAULT_PROVIDER."
        )
    raise ConfigurationError("No connections are registered.")


def _resolve_default_provider_name() -> str:
    """Compatibility alias for legacy provider-named callers."""
    return _resolve_default_connection_name()


def get_connection_runtime(connection_name: str | None = None) -> Provider:
    name = _normalize_connection_name(connection_name) or _resolve_default_connection_name()
    registered = set(list_registered_connections())
    driver_name = connection_driver_name(name) or name
    factory = _driver_factories().get(driver_name)
    if name not in registered or factory is None:
        raise ProviderNotFoundError(f"Connection '{name}' is not registered.")
    provider = _PROVIDER_CACHE.get(name)
    if provider is None:
        config = load_connection_config(name) if connection_driver_name(name) else None
        try:
            provider = factory(name=name, config=config)
        except TypeError:
            provider = factory()
        _PROVIDER_CACHE[name] = provider
    return provider


def get_provider(provider_name: str | None = None) -> Provider:
    """Compatibility wrapper for legacy provider-named callers.

    Public WFX endpoints still expose "providers", but the runtime name now
    represents a configured connection/mount.
    """
    try:
        return get_connection_runtime(provider_name)
    except ProviderNotFoundError as exc:
        raise ProviderNotFoundError(str(exc).replace("Connection", "Provider", 1)) from exc


def reload_provider_cache() -> None:
    """Clear provider instances so subsequent calls load fresh config."""
    _PROVIDER_CACHE.clear()


def list_registered_connections() -> list[str]:
    factories = _driver_factories()
    connections = [
        name for name in list_connection_config_names() if (connection_driver_name(name) or "") in factories
    ]
    if connections:
        return connections
    configured = [name for name in list_provider_config_names() if name in factories]
    if configured:
        return configured
    return sorted(factories.keys())


def list_registered_providers() -> list[str]:
    """Compatibility wrapper for WFX provider endpoints.

    Returned names are connection/mount keys when connection config exists.
    """
    return list_registered_connections()


def audit_connection_runtime() -> dict[str, object]:
    """Check that configured connections are visible as runtime WFX providers."""
    factories = _driver_factories()
    registered = set(list_registered_connections())
    rows: list[dict[str, object]] = []
    mount_owners: dict[str, str] = {}

    for name in list_connection_config_names():
        metadata = load_connection_metadata(name)
        driver_name = _normalize_driver_name(metadata.get("driver")) if isinstance(metadata, dict) else None
        mount = metadata.get("mount") if isinstance(metadata, dict) else None
        issues: list[str] = []

        if not driver_name:
            issues.append("missing_driver")
        elif driver_name not in factories:
            issues.append("driver_not_available")

        if not isinstance(mount, str) or not mount.strip():
            issues.append("missing_mount")
        else:
            mount = mount.strip()
            if not mount.endswith(":/"):
                issues.append("invalid_mount")
            owner = mount_owners.get(mount)
            if owner:
                issues.append(f"duplicate_mount:{owner}")
            else:
                mount_owners[mount] = name

        if name not in registered:
            issues.append("not_registered")

        runtime_name = None
        runtime_driver = None
        runtime_mount = None
        if name in registered and driver_name in factories:
            try:
                provider = get_connection_runtime(name)
                runtime_name = provider.name
                config = getattr(provider, "config", {})
                if isinstance(config, dict):
                    runtime_driver = config.get("driver")
                    runtime_mount = config.get("mount")
                if runtime_name != name:
                    issues.append("runtime_name_mismatch")
                if isinstance(runtime_driver, str) and runtime_driver.strip().lower() != driver_name:
                    issues.append("runtime_driver_mismatch")
                if isinstance(runtime_mount, str) and isinstance(mount, str) and runtime_mount.strip() != mount:
                    issues.append("runtime_mount_mismatch")
            except Exception as exc:
                issues.append(f"runtime_error:{exc}")

        rows.append(
            {
                "name": name,
                "driver": driver_name,
                "mount": mount,
                "registered": name in registered,
                "runtime_name": runtime_name,
                "runtime_driver": runtime_driver,
                "runtime_mount": runtime_mount,
                "ok": not issues,
                "issues": issues,
            }
        )

    return {
        "ok": all(bool(row["ok"]) for row in rows),
        "connections": rows,
        "registered_providers": sorted(registered),
        "available_drivers": sorted(factories.keys()),
    }


def get_default_provider_name() -> str:
    return _resolve_default_provider_name()


def get_default_connection_name() -> str:
    return _resolve_default_connection_name()

