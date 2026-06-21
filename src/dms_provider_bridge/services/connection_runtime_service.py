from __future__ import annotations

import importlib
import inspect
import os
import pkgutil
from collections.abc import Callable
from dataclasses import dataclass

import dms_provider_bridge.drivers as drivers_package
from dms_provider_bridge.core.config_loader import (
    connection_driver_name,
    load_connection_metadata,
    list_connection_config_names,
    list_driver_config_names,
    load_config,
    load_connection_config,
)
from dms_provider_bridge.core.errors import ConfigurationError, ConnectionNotFoundError
from dms_provider_bridge.drivers.tc_vfs_contract import TcVfsContract


_DRIVER_FACTORIES: dict[str, Callable[[], TcVfsContract]] | None = None
_CONNECTION_RUNTIME_CACHE: dict[str, TcVfsContract] = {}

# Backward-compatible module attribute for tests and older integrations.
list_provider_config_names = list_driver_config_names


@dataclass(frozen=True)
class RuntimeConnection:
    """Configured mount exposed to WFX as a provider-compatible name."""

    name: str
    driver: str | None
    mount: str | None
    display_name: str | None
    description: str | None
    driver_available: bool
    registered: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "driver": self.driver,
            "mount": self.mount,
            "display_name": self.display_name,
            "description": self.description,
            "driver_available": self.driver_available,
            "registered": self.registered,
        }


def _discover_driver_factories() -> dict[str, Callable[[], TcVfsContract]]:
    factories: dict[str, Callable[[], TcVfsContract]] = {}
    for module_info in pkgutil.iter_modules(drivers_package.__path__):
        if module_info.name == "base":
            continue
        module = importlib.import_module(f"{drivers_package.__name__}.{module_info.name}")
        for _name, candidate in inspect.getmembers(module, inspect.isclass):
            if candidate is TcVfsContract or not issubclass(candidate, TcVfsContract) or inspect.isabstract(candidate):
                continue
            driver_name = _normalize_driver_name(getattr(candidate, "name", None))
            if driver_name:
                factories[driver_name] = candidate
    return factories


def _driver_factories() -> dict[str, Callable[[], TcVfsContract]]:
    global _DRIVER_FACTORIES
    if _DRIVER_FACTORIES is None:
        _DRIVER_FACTORIES = _discover_driver_factories()
    return _DRIVER_FACTORIES


def _normalize_connection_name(connection_name: str | None) -> str | None:
    if connection_name is None:
        return None
    normalized = connection_name.strip().lower()
    if normalized.endswith(":"):
        normalized = normalized[:-1]
    return normalized or None


def _normalize_driver_name(driver_name: str | None) -> str | None:
    return _normalize_connection_name(driver_name)


def _resolve_default_connection_name() -> str:
    """Return default connection name from config or environment."""
    registered = set(list_registered_connections())
    try:
        config = load_config()
        connection_cfg = config.get("connection") if isinstance(config, dict) else None
        from_config = _normalize_connection_name(connection_cfg.get("default") if isinstance(connection_cfg, dict) else None)
        if from_config and from_config in registered:
            return from_config
    except Exception:
        pass
    from_env = _normalize_connection_name(os.getenv("DMS_PROVIDER_DEFAULT_CONNECTION"))
    if from_env and from_env in registered:
        return from_env
    if registered:
        raise ConfigurationError(
            "Default connection is not configured. Set connection.default in bridge.json "
            "or DMS_PROVIDER_DEFAULT_CONNECTION."
        )
    raise ConfigurationError("No connections are registered.")


def get_connection_runtime(connection_name: str | None = None) -> TcVfsContract:
    name = _normalize_connection_name(connection_name) or _resolve_default_connection_name()
    registered = set(list_registered_connections())
    driver_name = connection_driver_name(name) or name
    factory = _driver_factories().get(driver_name)
    if name not in registered or factory is None:
        raise ConnectionNotFoundError(f"Connection '{name}' is not registered.")
    connection_runtime = _CONNECTION_RUNTIME_CACHE.get(name)
    if connection_runtime is None:
        config = load_connection_config(name) if connection_driver_name(name) else None
        try:
            connection_runtime = factory(name=name, config=config)
        except TypeError:
            connection_runtime = factory()
        _CONNECTION_RUNTIME_CACHE[name] = connection_runtime
    return connection_runtime


def reload_connection_runtime_cache() -> None:
    """Clear connection runtime instances so subsequent calls load fresh config."""
    _CONNECTION_RUNTIME_CACHE.clear()


def reload_provider_cache() -> None:
    """Backward-compatible alias for older provider-named call sites."""
    reload_connection_runtime_cache()


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


def runtime_registry_snapshot() -> dict[str, object]:
    """Return the current ABC -> driver -> connection runtime view.

    Runtime names are configured connections/mounts. Drivers are only
    implementation modules behind those connections.
    """
    factories = _driver_factories()
    registered = set(list_registered_connections())
    connections: list[RuntimeConnection] = []
    for name in list_connection_config_names():
        metadata = load_connection_metadata(name)
        driver_name = _normalize_driver_name(metadata.get("driver")) if isinstance(metadata, dict) else None
        connections.append(
            RuntimeConnection(
                name=name,
                driver=driver_name,
                mount=metadata.get("mount") if isinstance(metadata, dict) else None,
                display_name=metadata.get("display_name") if isinstance(metadata, dict) else None,
                description=metadata.get("description") if isinstance(metadata, dict) else None,
                driver_available=bool(driver_name and driver_name in factories),
                registered=name in registered,
            )
        )
    return {
        "tc_vfs_contract": "provider",
        "provider_abc": "provider",
        "available_drivers": sorted(factories.keys()),
        "connections": [connection.as_dict() for connection in connections],
        "wfx_connections": sorted(registered),
    }


def audit_connection_runtime() -> dict[str, object]:
    """Check that configured connections are visible as runtime WFX connections."""
    factories = _driver_factories()
    snapshot = runtime_registry_snapshot()
    registered = set(snapshot["wfx_connections"])
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
                connection_runtime = get_connection_runtime(name)
                runtime_name = connection_runtime.name
                config = getattr(connection_runtime, "config", {})
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
        "registered_connections": sorted(registered),
        "available_drivers": sorted(factories.keys()),
        "runtime_registry": snapshot,
    }


def get_default_connection_name() -> str:
    return _resolve_default_connection_name()

