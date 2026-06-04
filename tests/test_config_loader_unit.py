from __future__ import annotations

# pyright: reportMissingTypeStubs=false

import pytest
from pathlib import Path

from dms_provider_bridge.core import config_loader


pytestmark = pytest.mark.unit


def test_load_provider_config_accepts_utf8_bom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider_file = tmp_path / "fso.json"
    provider_file.write_text(
        '{"key":"fso","fso":{"allowedRoots":["C:/Users/merhautr/python_projects"]}}',
        encoding="utf-8-sig",
    )

    monkeypatch.setattr(config_loader, "CONFIG_DIR", tmp_path)

    config = config_loader.load_provider_config("fso")

    assert config["allowedRoots"] == ["C:/Users/merhautr/python_projects"]

