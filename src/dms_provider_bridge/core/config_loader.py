from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dms_provider_bridge.core.paths import MACHINE_CONFIG_DIR, USER_CONFIG_DIR


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

    return {}


def _config_dirs() -> tuple[Path, Path | None]:
    machine_dir = Path(os.environ.get("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(MACHINE_CONFIG_DIR)))

    user_dir_raw = os.environ.get("DMS_PROVIDER_USER_CONFIG_DIR")
    user_dir = Path(user_dir_raw) if user_dir_raw else USER_CONFIG_DIR

    return machine_dir, user_dir


def load_config() -> dict[str, Any]:
    machine_dir, user_dir = _config_dirs()

    base = _read_json(machine_dir / "bridge.json")
    if base is None:
        return {}

    if user_dir is None:
        return base

    user = _read_json(user_dir / "bridge.json")
    if user is None:
        return base

    return _merge_dicts(base, user)


def load_provider_config(provider_name: str) -> dict[str, Any]:
    machine_dir, user_dir = _config_dirs()

    base_path = machine_dir / f"{provider_name}.json"
    base_payload = _read_json(base_path)

    if base_payload is None:
        return {}

    base_section = _extract_provider_section(base_payload, provider_name)

    if user_dir is None:
        return base_section

    user_path = user_dir / f"{provider_name}.json"
    user_payload = _read_json(user_path)
    if user_payload is None:
        return base_section

    local_section = _extract_provider_section(user_payload, provider_name)

    return _merge_dicts(base_section, local_section)
