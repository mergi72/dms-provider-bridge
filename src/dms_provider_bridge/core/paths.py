from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = PACKAGE_DIR.parent
PROJECT_ROOT = SRC_DIR.parent
CONFIG_DIR = PROJECT_ROOT / "config"
TEMP_DIR = PROJECT_ROOT / ".tmp"

TEMP_DIR.mkdir(parents=True, exist_ok=True)
