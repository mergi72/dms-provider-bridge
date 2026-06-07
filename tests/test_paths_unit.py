from __future__ import annotations

import importlib
import tempfile
from pathlib import Path

import pytest

import dms_provider_bridge.core.paths as paths_module


pytestmark = pytest.mark.unit


def test_temp_dir_defaults_to_system_temp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DMS_PROVIDER_TEMP_DIR", raising=False)

    paths = importlib.reload(paths_module)

    assert paths.TEMP_DIR == Path(tempfile.gettempdir()) / "DMS Provider"


def test_temp_dir_can_be_overridden(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    custom_temp = tmp_path / "bridge-temp"
    monkeypatch.setenv("DMS_PROVIDER_TEMP_DIR", str(custom_temp))

    paths = importlib.reload(paths_module)

    assert paths.TEMP_DIR == custom_temp

    monkeypatch.delenv("DMS_PROVIDER_TEMP_DIR", raising=False)
    importlib.reload(paths_module)
