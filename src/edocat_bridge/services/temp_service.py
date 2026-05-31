from __future__ import annotations

import shutil
from pathlib import Path

from edocat_bridge.core.paths import TEMP_DIR


def get_temp_dir() -> Path:
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    return TEMP_DIR


def clear_temp_dir() -> None:
    if TEMP_DIR.exists():
        shutil.rmtree(TEMP_DIR)
    TEMP_DIR.mkdir(parents=True, exist_ok=True)
