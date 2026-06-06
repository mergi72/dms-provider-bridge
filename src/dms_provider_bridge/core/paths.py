from __future__ import annotations

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PACKAGE_DIR.parent
PROJECT_ROOT = SRC_DIR.parent

_config_dir_env = os.environ.get("DMS_PROVIDER_CONFIG_DIR")
CONFIG_DIR = Path(_config_dir_env) if _config_dir_env else PROJECT_ROOT / "config"

TEMP_DIR = PROJECT_ROOT / ".tmp"

TEMP_DIR.mkdir(parents=True, exist_ok=True)
