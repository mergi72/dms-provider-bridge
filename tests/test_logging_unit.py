from __future__ import annotations

import logging

import pytest

from dms_provider_bridge.core import logging as bridge_logging


pytestmark = pytest.mark.unit


def test_configure_logging_writes_bridge_log_to_debug_path(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge_logging, "_LOGGING_INITIALIZED", False)
    monkeypatch.setattr(bridge_logging, "_BRIDGE_FILE_LOGGING_INITIALIZED", False)
    monkeypatch.setattr(bridge_logging, "_FILE_LOGGING_INITIALIZED", False)
    root_logger = logging.getLogger()
    original_handlers = list(root_logger.handlers)
    for handler in original_handlers:
        root_logger.removeHandler(handler)

    try:
        bridge_logging.configure_logging(
            {
                "debug": {
                    "enable": False,
                    "path": str(tmp_path),
                }
            }
        )
        logging.getLogger("dms_provider_bridge.test").info("hello bridge log")

        bridge_log = tmp_path / "bridge.log"
        assert bridge_log.exists()
        assert "hello bridge log" in bridge_log.read_text(encoding="utf-8")
    finally:
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            handler.close()
        for handler in original_handlers:
            root_logger.addHandler(handler)
        monkeypatch.setattr(bridge_logging, "_LOGGING_INITIALIZED", True)
        monkeypatch.setattr(bridge_logging, "_BRIDGE_FILE_LOGGING_INITIALIZED", False)
        monkeypatch.setattr(bridge_logging, "_FILE_LOGGING_INITIALIZED", False)
