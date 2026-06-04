from __future__ import annotations

# pyright: reportMissingTypeStubs=false

import pytest
from pathlib import Path

from dms_provider_bridge.core import config_loader


pytestmark = pytest.mark.unit


def test_load_provider_config_accepts_utf8_bom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider_file = tmp_path / "fso.json"
    provider_file.write_text(
        '{"key":"fso","fso":{"allowedRoots":["C:/MyDocuments"]}}',
        encoding="utf-8-sig",
    )

    monkeypatch.setattr(config_loader, "CONFIG_DIR", tmp_path)

    config = config_loader.load_provider_config("fso")

    assert config["allowedRoots"] == ["C:/MyDocuments"]


def test_load_config_applies_local_override_layers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "default.json").write_text(
        '{"upload": {"raw": {"maxBytes": 100, "chunkBytes": 1048576}}, "x": 1}',
        encoding="utf-8",
    )
    (tmp_path / "user.json").write_text(
        '{"upload": {"raw": {"maxBytes": 200}}, "x": 2}',
        encoding="utf-8",
    )
    (tmp_path / "user.local.json").write_text(
        '{"upload": {"raw": {"maxBytes": 300}}, "x": 3}',
        encoding="utf-8",
    )
    (tmp_path / "local.json").write_text(
        '{"upload": {"raw": {"maxBytes": 400}}, "x": 4}',
        encoding="utf-8",
    )

    monkeypatch.setattr(config_loader, "CONFIG_DIR", tmp_path)

    config = config_loader.load_config()

    assert config["upload"]["raw"]["maxBytes"] == 400
    assert config["upload"]["raw"]["chunkBytes"] == 1048576
    assert config["x"] == 4


def test_load_provider_config_applies_local_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "edocat.json").write_text(
        '{"key": "edocat", "edocat": {"base_url": "https://generic.edocat.net", "transfer": {"maxNodes": 100}}}',
        encoding="utf-8",
    )
    (tmp_path / "edocat.local.json").write_text(
        '{"key": "edocat", "edocat": {"base_url": "https://local.edocat.net", "transfer": {"maxBase64Bytes": 42}}}',
        encoding="utf-8",
    )

    monkeypatch.setattr(config_loader, "CONFIG_DIR", tmp_path)

    config = config_loader.load_provider_config("edocat")

    assert config["base_url"] == "https://local.edocat.net"
    assert config["transfer"]["maxNodes"] == 100
    assert config["transfer"]["maxBase64Bytes"] == 42

