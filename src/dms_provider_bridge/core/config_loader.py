from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dms_provider_bridge.core.logging import get_logger
from dms_provider_bridge.core.paths import MACHINE_CONFIG_DIR, USER_CONFIG_DIR

_LOGGER = get_logger(__name__)


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


def _log_provider_config(provider_name: str, config: dict[str, Any], machine_path: Path, user_path: Path | None) -> None:
    try:
        rendered = json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True)
    except TypeError:
        rendered = repr(config)
    _LOGGER.info(
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

    base = _read_json(machine_dir / "bridge.json")
    if base is None:
        return {}

    if user_dir is None:
        return base

    user = _read_json(user_dir / "bridge.local.json")
    if user is None:
        return base

    return _merge_dicts(base, user)


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
