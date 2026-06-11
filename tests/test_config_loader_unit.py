from __future__ import annotations

# pyright: reportMissingTypeStubs=false

import logging
import pytest
from pathlib import Path

from dms_provider_bridge.core import config_loader


pytestmark = pytest.mark.unit


def test_load_provider_config_accepts_utf8_bom(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    machine_dir = tmp_path / "machine"
    machine_dir.mkdir()
    provider_file = machine_dir / "sample.json"
    provider_file.write_text(
        '{"key":"sample","sample":{"base_url":"https://example.test"}}',
        encoding="utf-8-sig",
    )

    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(machine_dir))
    monkeypatch.delenv("DMS_PROVIDER_USER_CONFIG_DIR", raising=False)

    config = config_loader.load_provider_config("sample")

    assert config["base_url"] == "https://example.test"


def test_load_config_merges_user_bridge_local_json_over_machine_bridge_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine_dir = tmp_path / "machine"
    user_dir = tmp_path / "user"
    machine_dir.mkdir()
    user_dir.mkdir()

    (machine_dir / "bridge.json").write_text(
        '{"upload": {"raw": {"maxBytes": 100, "chunkBytes": 1048576}}, "x": 1}',
        encoding="utf-8",
    )
    (user_dir / "bridge.local.json").write_text(
        '{"upload": {"raw": {"maxBytes": 200}}, "x": 2}',
        encoding="utf-8",
    )

    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(machine_dir))
    monkeypatch.setenv("DMS_PROVIDER_USER_CONFIG_DIR", str(user_dir))

    config = config_loader.load_config()

    assert config["upload"]["raw"]["maxBytes"] == 200
    assert config["upload"]["raw"]["chunkBytes"] == 1048576
    assert config["x"] == 2


def test_load_config_ignores_user_bridge_local_json_when_machine_bridge_json_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine_dir = tmp_path / "machine"
    user_dir = tmp_path / "user"
    machine_dir.mkdir()
    user_dir.mkdir()

    (user_dir / "bridge.local.json").write_text('{"x": 2}', encoding="utf-8")

    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(machine_dir))
    monkeypatch.setenv("DMS_PROVIDER_USER_CONFIG_DIR", str(user_dir))

    assert config_loader.load_config() == {}


def test_load_provider_config_merges_user_provider_local_json_over_machine_provider_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine_dir = tmp_path / "machine"
    user_dir = tmp_path / "user"
    machine_dir.mkdir()
    user_dir.mkdir()

    (machine_dir / "edocat.json").write_text(
        '{"key": "edocat", "edocat": {"base_url": "https://generic.edocat.net", "transfer": {"maxNodes": 100}}}',
        encoding="utf-8",
    )
    (user_dir / "edocat.local.json").write_text(
        '{"key": "edocat", "edocat": {"base_url": "https://local.edocat.net", "transfer": {"maxBase64Bytes": 42}}}',
        encoding="utf-8",
    )

    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(machine_dir))
    monkeypatch.setenv("DMS_PROVIDER_USER_CONFIG_DIR", str(user_dir))

    config = config_loader.load_provider_config("edocat")

    assert config["base_url"] == "https://local.edocat.net"
    assert config["transfer"]["maxNodes"] == 100
    assert config["transfer"]["maxBase64Bytes"] == 42


def test_load_provider_config_accepts_direct_provider_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine_dir = tmp_path / "machine"
    user_dir = tmp_path / "user"
    machine_dir.mkdir()
    user_dir.mkdir()
    (machine_dir / "alfresco.json").write_text(
        '{"base_url": "https://machine.alfresco.net", "api": {"repo_root": "/repo"}}',
        encoding="utf-8",
    )
    (user_dir / "alfresco.local.json").write_text(
        '{"base_url": "https://local.alfresco.net", "timeouts": {"requestSeconds": 60}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(machine_dir))
    monkeypatch.setenv("DMS_PROVIDER_USER_CONFIG_DIR", str(user_dir))

    config = config_loader.load_provider_config("alfresco")

    assert config["base_url"] == "https://local.alfresco.net"
    assert config["api"]["repo_root"] == "/repo"
    assert config["timeouts"]["requestSeconds"] == 60


def test_load_provider_config_accepts_keyed_direct_provider_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine_dir = tmp_path / "machine"
    user_dir = tmp_path / "user"
    machine_dir.mkdir()
    user_dir.mkdir()
    (machine_dir / "alfresco.json").write_text(
        '{"key": "alfresco", "_comment": "metadata", "base_url": "https://machine.alfresco.net", "api": {"repo_root": "/repo"}}',
        encoding="utf-8",
    )
    (user_dir / "alfresco.local.json").write_text(
        '{"key": "alfresco", "base_url": "https://local.alfresco.net"}',
        encoding="utf-8",
    )
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(machine_dir))
    monkeypatch.setenv("DMS_PROVIDER_USER_CONFIG_DIR", str(user_dir))

    config = config_loader.load_provider_config("alfresco")

    assert config == {
        "base_url": "https://local.alfresco.net",
        "api": {"repo_root": "/repo"},
    }


def test_load_provider_config_ignores_user_provider_local_json_when_machine_provider_json_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine_dir = tmp_path / "machine"
    user_dir = tmp_path / "user"
    machine_dir.mkdir()
    user_dir.mkdir()

    (user_dir / "edocat.local.json").write_text(
        '{"key": "edocat", "edocat": {"base_url": "https://local.edocat.net"}}',
        encoding="utf-8",
    )

    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(machine_dir))
    monkeypatch.setenv("DMS_PROVIDER_USER_CONFIG_DIR", str(user_dir))

    assert config_loader.load_provider_config("edocat") == {}


def test_load_provider_config_masks_sensitive_values_in_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    machine_dir = tmp_path / "machine"
    user_dir = tmp_path / "user"
    machine_dir.mkdir()
    user_dir.mkdir()
    (machine_dir / "alfresco.json").write_text(
        '{"key": "alfresco", "alfresco": {"base_url": "https://example.test", "password": "machine-pass", "nested": {"api_key": "machine-api-key"}}}',
        encoding="utf-8",
    )
    (user_dir / "alfresco.local.json").write_text(
        '{"key": "alfresco", "alfresco": {"token": "local-token", "nested": {"clientSecret": "local-secret"}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(machine_dir))
    monkeypatch.setenv("DMS_PROVIDER_USER_CONFIG_DIR", str(user_dir))

    with caplog.at_level(logging.INFO, logger="dms_provider_bridge.core.config_loader"):
        config = config_loader.load_provider_config("alfresco")

    assert config["password"] == "machine-pass"
    assert config["token"] == "local-token"
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "machine-pass" not in logged
    assert "machine-api-key" not in logged
    assert "local-token" not in logged
    assert "local-secret" not in logged
    assert '"password": "***"' in logged
    assert '"api_key": "***"' in logged
    assert '"token": "***"' in logged
    assert '"clientSecret": "***"' in logged

