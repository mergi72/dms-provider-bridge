from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dms_provider_bridge.core.debug import debug_enabled, provider_debug_logger
from dms_provider_bridge.core.logging import get_logger
from dms_provider_bridge.core.paths import MACHINE_CONFIG_DIR, USER_CONFIG_DIR

_LOGGER = get_logger(__name__)
_SENSITIVE_CONFIG_KEY_PARTS = ("password", "secret", "token", "apikey")
_MASKED_CONFIG_VALUE = "***"


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


def _extract_provider_section(payload: dict[str, Any], provider_name: str) -> dict[str, Any]:
    if not payload:
        return {}

    key = payload.get("key")
    if isinstance(key, str) and isinstance(payload.get(key), dict):
        return payload[key]

    section = payload.get(provider_name)
    if isinstance(section, dict):
        return section

    metadata_keys = {"key", "projectInfo", "config.json", "_comment"}
    direct_payload = {name: value for name, value in payload.items() if name not in metadata_keys}
    if direct_payload:
        return direct_payload

    return {}


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
    debug_logger = provider_debug_logger("bridge", config)
    debug_logger.debug(
        "bridge_config_loaded machine_path=%s user_path=%s config=%s",
        machine_path,
        user_path or "",
        rendered,
    )


def _log_provider_config(
    provider_name: str,
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
    debug_logger = provider_debug_logger(provider_name, config)
    debug_logger.debug(
        "provider_config_loaded provider=%s machine_path=%s user_path=%s config=%s",
        provider_name,
        machine_path,
        user_path or "",
        rendered,
    )


def _config_dirs() -> tuple[Path, Path | None]:
    machine_dir = Path(os.environ.get("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(MACHINE_CONFIG_DIR)))

    user_dir_raw = os.environ.get("DMS_PROVIDER_USER_CONFIG_DIR")
    user_dir = Path(user_dir_raw) if user_dir_raw else USER_CONFIG_DIR

    return machine_dir, user_dir


def list_provider_config_names() -> list[str]:
    machine_dir, _user_dir = _config_dirs()
    if not machine_dir.exists():
        return []

    names: set[str] = set()
    for path in machine_dir.glob("*.json"):
        if path.name == "bridge.json" or path.name.endswith(".local.json"):
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


def load_provider_config(provider_name: str) -> dict[str, Any]:
    machine_dir, user_dir = _config_dirs()

    base_path = machine_dir / f"{provider_name}.json"
    user_path = user_dir / f"{provider_name}.local.json" if user_dir is not None else None
    base_payload = _read_json(base_path)

    if base_payload is None:
        _log_provider_config(provider_name, {}, base_path, user_path)
        return {}

    base_section = _extract_provider_section(base_payload, provider_name)

    if user_dir is None:
        _log_provider_config(provider_name, base_section, base_path, user_path)
        return base_section

    user_payload = _read_json(user_path)
    if user_payload is None:
        _log_provider_config(provider_name, base_section, base_path, user_path)
        return base_section

    local_section = _extract_provider_section(user_payload, provider_name)

    merged = _merge_dicts(base_section, local_section)
    _log_provider_config(provider_name, merged, base_path, user_path)
    return merged
