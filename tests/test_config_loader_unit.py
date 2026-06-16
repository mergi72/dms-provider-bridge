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


def test_load_provider_config_reads_driver_directory_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine_dir = tmp_path / "machine"
    user_dir = tmp_path / "user"
    drivers_dir = machine_dir / "drivers"
    user_drivers_dir = user_dir / "drivers"
    drivers_dir.mkdir(parents=True)
    user_drivers_dir.mkdir(parents=True)
    (machine_dir / "bridge.json").write_text(
        '{"paths": {"drivers": "drivers"}}',
        encoding="utf-8",
    )
    (drivers_dir / "alfresco.json").write_text(
        '{"key": "alfresco", "alfresco": {"base_url": "https://machine.alfresco.net", "transfer": {"maxNodes": 100}}}',
        encoding="utf-8",
    )
    (user_drivers_dir / "alfresco.local.json").write_text(
        '{"key": "alfresco", "alfresco": {"base_url": "https://local.alfresco.net"}}',
        encoding="utf-8",
    )

    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(machine_dir))
    monkeypatch.setenv("DMS_PROVIDER_USER_CONFIG_DIR", str(user_dir))

    config = config_loader.load_provider_config("alfresco")

    assert config["base_url"] == "https://local.alfresco.net"
    assert config["transfer"]["maxNodes"] == 100


def test_list_provider_config_names_reads_driver_directory_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine_dir = tmp_path / "machine"
    drivers_dir = machine_dir / "drivers"
    drivers_dir.mkdir(parents=True)
    (machine_dir / "bridge.json").write_text(
        '{"paths": {"drivers": "drivers"}}',
        encoding="utf-8",
    )
    (drivers_dir / "driver.json").write_text('{"key": "driver_name"}', encoding="utf-8")
    (drivers_dir / "alfresco.json").write_text('{"key": "alfresco"}', encoding="utf-8")
    (drivers_dir / "edocat.json").write_text('{"key": "edocat"}', encoding="utf-8")

    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(machine_dir))
    monkeypatch.delenv("DMS_PROVIDER_USER_CONFIG_DIR", raising=False)

    assert config_loader.list_provider_config_names() == ["alfresco", "edocat"]


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
        '{"key": "alfresco", "alfresco": {"debug": {"enable": true}, "base_url": "https://example.test", "password": "machine-pass", "nested": {"api_key": "machine-api-key"}}}',
        encoding="utf-8",
    )
    (user_dir / "alfresco.local.json").write_text(
        '{"key": "alfresco", "alfresco": {"token": "local-token", "nested": {"clientSecret": "local-secret"}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(machine_dir))
    monkeypatch.setenv("DMS_PROVIDER_USER_CONFIG_DIR", str(user_dir))

    with caplog.at_level(logging.DEBUG, logger="dms_provider_bridge.core.config_loader"):
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


def test_load_provider_config_does_not_log_config_when_debug_is_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    machine_dir = tmp_path / "machine"
    user_dir = tmp_path / "user"
    machine_dir.mkdir()
    user_dir.mkdir()
    (machine_dir / "alfresco.json").write_text(
        '{"key": "alfresco", "alfresco": {"base_url": "https://example.test", "password": "machine-pass"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(machine_dir))
    monkeypatch.setenv("DMS_PROVIDER_USER_CONFIG_DIR", str(user_dir))

    with caplog.at_level(logging.DEBUG, logger="dms_provider_bridge.core.config_loader"):
        config = config_loader.load_provider_config("alfresco")

    assert config["password"] == "machine-pass"
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "provider_config_loaded" not in logged
    assert "machine-pass" not in logged


def test_load_provider_config_ignores_bridge_debug_for_provider_dump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    machine_dir = tmp_path / "machine"
    user_dir = tmp_path / "user"
    machine_dir.mkdir()
    user_dir.mkdir()
    (machine_dir / "bridge.json").write_text('{"debug": {"enable": true}}', encoding="utf-8")
    (machine_dir / "alfresco.json").write_text(
        '{"key": "alfresco", "alfresco": {"base_url": "https://example.test", "password": "machine-pass"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(machine_dir))
    monkeypatch.setenv("DMS_PROVIDER_USER_CONFIG_DIR", str(user_dir))

    with caplog.at_level(logging.DEBUG, logger="dms_provider_bridge.core.config_loader"):
        config = config_loader.load_provider_config("alfresco")

    assert config["password"] == "machine-pass"
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "provider_config_loaded" not in logged
    assert "machine-pass" not in logged


def test_load_provider_config_writes_provider_debug_file_without_bridge_debug(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    machine_dir = tmp_path / "machine"
    user_dir = tmp_path / "user"
    debug_dir = tmp_path / "debug"
    machine_dir.mkdir()
    user_dir.mkdir()
    (machine_dir / "bridge.json").write_text('{"debug": {"enable": false}}', encoding="utf-8")
    (machine_dir / "alfresco.json").write_text(
        (
            '{"key": "alfresco", "alfresco": {'
            '"debug": {"enable": true, "path": "'
            + str(debug_dir).replace("\\", "\\\\")
            + '"}, '
            '"base_url": "https://example.test", '
            '"password": "machine-pass"'
            "}}"
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(machine_dir))
    monkeypatch.setenv("DMS_PROVIDER_USER_CONFIG_DIR", str(user_dir))

    config = config_loader.load_provider_config("alfresco")

    assert config["password"] == "machine-pass"
    debug_log = debug_dir / "alfresco-debug.log"
    assert debug_log.exists()
    logged = debug_log.read_text(encoding="utf-8")
    assert "provider_config_loaded provider=alfresco" in logged
    assert "machine-pass" not in logged
    assert '"password": "***"' in logged


def test_load_config_logs_bridge_config_only_when_debug_is_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    machine_dir = tmp_path / "machine"
    user_dir = tmp_path / "user"
    machine_dir.mkdir()
    user_dir.mkdir()
    (machine_dir / "bridge.json").write_text('{"debug": {"enable": false}, "secret": "hidden"}', encoding="utf-8")
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(machine_dir))
    monkeypatch.setenv("DMS_PROVIDER_USER_CONFIG_DIR", str(user_dir))

    with caplog.at_level(logging.DEBUG, logger="dms_provider_bridge.core.config_loader"):
        config = config_loader.load_config()

    assert config["debug"]["enable"] is False
    assert "bridge_config_loaded" not in "\n".join(record.getMessage() for record in caplog.records)

    caplog.clear()
    (machine_dir / "bridge.json").write_text('{"debug": {"enable": true}, "secret": "hidden"}', encoding="utf-8")

    with caplog.at_level(logging.DEBUG, logger="dms_provider_bridge.core.config_loader"):
        config = config_loader.load_config()

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert config["debug"]["enable"] is True
    assert "bridge_config_loaded" in logged
    assert "hidden" not in logged
    assert '"secret": "***"' in logged

