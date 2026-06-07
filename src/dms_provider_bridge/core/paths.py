from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PACKAGE_DIR.parent
PROJECT_ROOT = SRC_DIR.parent

def _machine_config_dir() -> Path:
    explicit = os.environ.get("DMS_PROVIDER_MACHINE_CONFIG_DIR")
    if explicit:
        return Path(explicit)

    common_app_data = os.environ.get("ProgramData") or os.environ.get("COMMONAPPDATA")
    if common_app_data:
        return Path(common_app_data) / "DMS Provider" / "config"

    return PROJECT_ROOT / "config"


def _user_config_dir() -> Path | None:
    explicit = os.environ.get("DMS_PROVIDER_USER_CONFIG_DIR")
    if explicit:
        return Path(explicit)

    user_app_data = os.environ.get("APPDATA")
    if user_app_data:
        return Path(user_app_data) / "DMS Provider" / "config"

    return None


MACHINE_CONFIG_DIR = _machine_config_dir()
USER_CONFIG_DIR = _user_config_dir()

# Backward-compatible alias for older imports. Runtime loading uses MACHINE_CONFIG_DIR.
CONFIG_DIR = MACHINE_CONFIG_DIR

TEMP_DIR = PROJECT_ROOT / ".tmp"

TEMP_DIR.mkdir(parents=True, exist_ok=True)
