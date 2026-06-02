from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from edocat_bridge.core.paths import CONFIG_DIR


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    # Accept UTF-8 with optional BOM to avoid startup failures on externally rewritten config files.
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


def load_config() -> dict[str, Any]:
    default_cfg = _read_json(CONFIG_DIR / "default.json")
    user_cfg = _read_json(CONFIG_DIR / "user.json")
    return _merge_dicts(default_cfg, user_cfg)


def load_provider_config(provider_name: str) -> dict[str, Any]:
    """Load provider vendor config from config/<provider>.json.

    File format is expected to contain either a "key" pointing to provider section
    or the provider section directly under provider_name.
    """
    payload = _read_json(CONFIG_DIR / f"{provider_name}.json")
    if not payload:
        return {}

    key = payload.get("key")
    if isinstance(key, str) and isinstance(payload.get(key), dict):
        return payload[key]

    section = payload.get(provider_name)
    if isinstance(section, dict):
        return section
    return {}
