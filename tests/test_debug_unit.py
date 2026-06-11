from __future__ import annotations

import logging
import time

import pytest

from dms_provider_bridge.core import debug as debug_module


pytestmark = pytest.mark.unit


def _close_logger_handlers(logger: logging.Logger) -> None:
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()


def test_debug_enabled_accepts_nested_enable_and_legacy_boolean() -> None:
    assert debug_module.debug_enabled({"debug": {"enable": True}}) is True
    assert debug_module.debug_enabled({"debug": {"enable": False}}) is False
    assert debug_module.debug_enabled({"debug": {}}) is False
    assert debug_module.debug_enabled({"debug": True}) is True
    assert debug_module.debug_enabled({}) is False


def test_provider_debug_logger_writes_provider_specific_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(debug_module, "_DEBUG_FILE_LOGGERS", set())
    logger = debug_module.provider_debug_logger(
        "sharepoint",
        {
            "debug": {
                "enable": True,
                "path": str(tmp_path),
            }
        },
    )

    try:
        logger.debug("sharepoint provider boot")

        log_path = tmp_path / "sharepoint-debug.log"
        assert log_path.exists()
        assert "sharepoint provider boot" in log_path.read_text(encoding="utf-8")
    finally:
        _close_logger_handlers(logger)


def test_provider_debug_logger_without_enable_does_not_create_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(debug_module, "_DEBUG_FILE_LOGGERS", set())
    logger = debug_module.provider_debug_logger(
        "sharepoint_disabled",
        {
            "debug": {
                "enable": False,
                "path": str(tmp_path),
            }
        },
    )

    logger.debug("ignored provider debug")

    assert not (tmp_path / "sharepoint_disabled-debug.log").exists()


def test_provider_operation_helpers_log_start_done_and_failed(caplog: pytest.LogCaptureFixture) -> None:
    logger = logging.getLogger("dms_provider_bridge.providers.test")
    logger.setLevel(logging.DEBUG)

    with caplog.at_level(logging.DEBUG, logger=logger.name):
        started = debug_module.log_provider_operation_start(logger, "test", "list", "/A")
        debug_module.log_provider_operation_done(logger, "test", "list", started, "/A", items=2)
        started = time.perf_counter()
        debug_module.log_provider_operation_failed(logger, "test", "download", started, "/B", error="boom")

    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "provider_operation_start provider=test operation=list path=/A" in logged
    assert "provider_operation_done provider=test operation=list path=/A status=ok" in logged
    assert "items=2" in logged
    assert "provider_operation_failed provider=test operation=download path=/B status=failed" in logged
    assert "error=boom" in logged
