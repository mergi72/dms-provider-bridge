from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dms_provider_bridge.core.debug import connection_debug_logger, debug_enabled
from dms_provider_bridge.core.logging import get_logger
from dms_provider_bridge.core.paths import MACHINE_CONFIG_DIR, USER_CONFIG_DIR

_LOGGER = get_logger(__name__)
_SENSITIVE_CONFIG_KEY_PARTS = ("password", "secret", "token", "apikey")
_MASKED_CONFIG_VALUE = "***"
_CONFIG_METADATA_KEYS = {"key", "projectInfo", "config.json", "_comment"}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _extract_keyed_section(payload: dict[str, Any], section_name: str) -> dict[str, Any]:
    if not payload:
        return {}

    key = payload.get("key")
    if isinstance(key, str) and isinstance(payload.get(key), dict):
        root_values = {
            name: value
            for name, value in payload.items()
            if name not in _CONFIG_METADATA_KEYS and name != key
        }
        return _merge_dicts(root_values, payload[key])

    section = payload.get(section_name)
    if isinstance(section, dict):
        root_values = {
            name: value
            for name, value in payload.items()
            if name not in _CONFIG_METADATA_KEYS and name != section_name
        }
        return _merge_dicts(root_values, section)

    direct_payload = {name: value for name, value in payload.items() if name not in _CONFIG_METADATA_KEYS}
    if direct_payload:
        return direct_payload

    return {}


def _strip_empty_overrides(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            stripped = _strip_empty_overrides(item)
            if stripped in ("", None):
                continue
            if isinstance(stripped, dict) and not stripped:
                continue
            cleaned[key] = stripped
        return cleaned
    return value


def _is_sensitive_config_key(key: str) -> bool:
    normalized = key.replace("_", "").replace("-", "").casefold()
    return any(part in normalized for part in _SENSITIVE_CONFIG_KEY_PARTS)


def sanitize_config_for_logging(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _MASKED_CONFIG_VALUE if _is_sensitive_config_key(str(key)) else sanitize_config_for_logging(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [sanitize_config_for_logging(item) for item in value]
    return value


def _load_bridge_config(machine_dir: Path, user_dir: Path | None) -> dict[str, Any]:
    base = _read_json(machine_dir / "bridge.json")
    if base is None:
        return {}

    if user_dir is None:
        return base

    user = _read_json(user_dir / "bridge.local.json")
    if user is None:
        return base

    return _merge_dicts(base, user)


def _log_bridge_config(config: dict[str, Any], machine_path: Path, user_path: Path | None) -> None:
    if not debug_enabled(config):
        return

    sanitized_config = sanitize_config_for_logging(config)
    try:
        rendered = json.dumps(sanitized_config, ensure_ascii=False, indent=2, sort_keys=True)
    except TypeError:
        rendered = repr(sanitized_config)
    debug_logger = connection_debug_logger("bridge", config)
    debug_logger.debug(
        "bridge_config_loaded machine_path=%s user_path=%s config=%s",
        machine_path,
        user_path or "",
        rendered,
    )


def _log_driver_config(
    driver_name: str,
    config: dict[str, Any],
    machine_path: Path,
    user_path: Path | None,
) -> None:
    if not debug_enabled(config):
        return

    sanitized_config = sanitize_config_for_logging(config)
    try:
        rendered = json.dumps(sanitized_config, ensure_ascii=False, indent=2, sort_keys=True)
    except TypeError:
        rendered = repr(sanitized_config)
    debug_logger = connection_debug_logger(driver_name, config)
    debug_logger.debug(
        "driver_config_loaded driver=%s machine_path=%s user_path=%s config=%s",
        driver_name,
        machine_path,
        user_path or "",
        rendered,
    )


def _config_dirs() -> tuple[Path, Path | None]:
    machine_dir = Path(os.environ.get("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(MACHINE_CONFIG_DIR)))

    user_dir_raw = os.environ.get("DMS_PROVIDER_USER_CONFIG_DIR")
    user_dir = Path(user_dir_raw) if user_dir_raw else USER_CONFIG_DIR

    return machine_dir, user_dir


def _configured_registry_paths(machine_dir: Path) -> dict[str, Path]:
    config = _load_bridge_config(machine_dir, None)
    paths = config.get("paths") if isinstance(config, dict) else None
    if not isinstance(paths, dict):
        paths = {}
    return {
        "providers": machine_dir / str(paths.get("providers") or "providers"),
        "drivers": machine_dir / str(paths.get("drivers") or "drivers"),
        "connections": machine_dir / str(paths.get("connections") or "connections"),
        "auth": machine_dir / str(paths.get("auth") or "auth"),
    }


def _driver_config_paths(machine_dir: Path, user_dir: Path | None, driver_name: str) -> tuple[Path, Path | None]:
    legacy_base_path = machine_dir / f"{driver_name}.json"
    legacy_user_path = user_dir / f"{driver_name}.local.json" if user_dir is not None else None
    if legacy_base_path.exists():
        return legacy_base_path, legacy_user_path

    drivers_dir = _configured_registry_paths(machine_dir)["drivers"]
    driver_base_path = drivers_dir / f"{driver_name}.json"
    driver_user_path = None
    if user_dir is not None:
        structured_user_path = user_dir / "drivers" / f"{driver_name}.local.json"
        driver_user_path = structured_user_path if structured_user_path.exists() else legacy_user_path
    return driver_base_path, driver_user_path


def _connection_config_paths(machine_dir: Path, user_dir: Path | None, connection_name: str) -> tuple[Path, Path | None]:
    connections_dir = _configured_registry_paths(machine_dir)["connections"]
    connection_base_path = connections_dir / f"{connection_name}.json"
    connection_user_path = None
    if user_dir is not None:
        legacy_user_path = user_dir / f"{connection_name}.local.json"
        structured_user_path = user_dir / "connections" / f"{connection_name}.local.json"
        connection_user_path = legacy_user_path if legacy_user_path.exists() else structured_user_path
    return connection_base_path, connection_user_path


def list_driver_config_names() -> list[str]:
    machine_dir, _user_dir = _config_dirs()
    if not machine_dir.exists():
        return []

    names: set[str] = set()
    search_dirs = [machine_dir, _configured_registry_paths(machine_dir)["drivers"]]
    for directory in search_dirs:
        if not directory.exists():
            continue
        for path in directory.glob("*.json"):
            if path.name in {"bridge.json", "driver.json"} or path.name.endswith(".local.json"):
                continue
            payload = _read_json(path)
            if payload is None:
                continue
            key = payload.get("key")
            if isinstance(key, str) and key.strip():
                names.add(key.strip().lower())
            else:
                names.add(path.stem.lower())
    return sorted(names)


def list_provider_config_names() -> list[str]:
    """Deprecated compatibility alias for the driver registry name list."""
    return list_driver_config_names()


def list_connection_config_names() -> list[str]:
    machine_dir, _user_dir = _config_dirs()
    connections_dir = _configured_registry_paths(machine_dir)["connections"]
    if not connections_dir.exists():
        return []

    names: set[str] = set()
    for path in connections_dir.glob("*.json"):
        if path.name == "connection.json" or path.name.endswith(".local.json"):
            continue
        payload = _read_json(path)
        if payload is None:
            continue
        key = payload.get("key")
        if isinstance(key, str) and key.strip():
            names.add(key.strip().lower())
        else:
            names.add(path.stem.lower())
    return sorted(names)


def load_config() -> dict[str, Any]:
    machine_dir, user_dir = _config_dirs()

    config = _load_bridge_config(machine_dir, user_dir)
    _log_bridge_config(config, machine_dir / "bridge.json", user_dir / "bridge.local.json" if user_dir else None)
    return config


def load_driver_config(driver_name: str) -> dict[str, Any]:
    machine_dir, user_dir = _config_dirs()

    base_path, user_path = _driver_config_paths(machine_dir, user_dir, driver_name)
    base_payload = _read_json(base_path)

    if base_payload is None:
        _log_driver_config(driver_name, {}, base_path, user_path)
        return {}

    base_section = _extract_keyed_section(base_payload, driver_name)

    if user_dir is None:
        _log_driver_config(driver_name, base_section, base_path, user_path)
        return base_section

    user_payload = _read_json(user_path)
    if user_payload is None:
        _log_driver_config(driver_name, base_section, base_path, user_path)
        return base_section

    local_section = _extract_keyed_section(user_payload, driver_name)

    merged = _merge_dicts(base_section, local_section)
    _log_driver_config(driver_name, merged, base_path, user_path)
    return merged


def load_provider_config(provider_name: str) -> dict[str, Any]:
    """Deprecated compatibility alias for loading driver configuration."""
    return load_driver_config(provider_name)


def load_connection_config(connection_name: str) -> dict[str, Any]:
    machine_dir, user_dir = _config_dirs()

    base_path, user_path = _connection_config_paths(machine_dir, user_dir, connection_name)
    base_payload = _read_json(base_path)
    if base_payload is None:
        _log_driver_config(connection_name, {}, base_path, user_path)
        return {}

    connection_section = _extract_keyed_section(base_payload, connection_name)
    if user_dir is not None:
        user_payload = _read_json(user_path)
        if user_payload is not None:
            connection_section = _merge_dicts(
                connection_section,
                _extract_keyed_section(user_payload, connection_name),
            )

    driver_name = connection_section.get("driver")
    if not isinstance(driver_name, str) or not driver_name.strip():
        _log_driver_config(connection_name, connection_section, base_path, user_path)
        return connection_section

    driver_config = load_driver_config(driver_name.strip())
    connection_overrides = _strip_empty_overrides(connection_section)
    merged = _merge_dicts(driver_config, connection_overrides)
    _log_driver_config(connection_name, merged, base_path, user_path)
    return merged


def connection_driver_name(connection_name: str) -> str | None:
    machine_dir, user_dir = _config_dirs()
    base_path, user_path = _connection_config_paths(machine_dir, user_dir, connection_name)
    payload = _read_json(base_path)
    if payload is None:
        return None
    section = _extract_keyed_section(payload, connection_name)
    if user_dir is not None:
        user_payload = _read_json(user_path)
        if user_payload is not None:
            section = _merge_dicts(section, _extract_keyed_section(user_payload, connection_name))
    driver_name = section.get("driver")
    return driver_name.strip().lower() if isinstance(driver_name, str) and driver_name.strip() else None


def load_connection_metadata(connection_name: str) -> dict[str, str | None]:
    machine_dir, user_dir = _config_dirs()
    base_path, user_path = _connection_config_paths(machine_dir, user_dir, connection_name)
    payload = _read_json(base_path)
    if payload is None:
        return {
            "name": connection_name,
            "kind": "driver",
            "driver": None,
            "mount": None,
            "display_name": None,
            "description": None,
        }
    section = _extract_keyed_section(payload, connection_name)
    if user_dir is not None:
        user_payload = _read_json(user_path)
        if user_payload is not None:
            section = _merge_dicts(section, _extract_keyed_section(user_payload, connection_name))
    return {
        "name": connection_name,
        "kind": "connection",
        "driver": _string_or_none(section.get("driver")),
        "mount": _string_or_none(section.get("mount")),
        "display_name": _string_or_none(section.get("display_name")),
        "description": _string_or_none(section.get("description")),
    }


def connection_metadata_by_name() -> dict[str, dict[str, str | None]]:
    return {name: load_connection_metadata(name) for name in list_connection_config_names()}


def driver_connection_names(driver_name: str) -> list[str]:
    normalized = driver_name.strip().lower()
    return sorted(
        name
        for name, metadata in connection_metadata_by_name().items()
        if (metadata.get("driver") or "").strip().lower() == normalized
    )


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
