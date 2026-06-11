from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

from dms_provider_bridge.core.paths import LOG_DIR


_LOGGING_INITIALIZED = False
_BRIDGE_FILE_LOGGING_INITIALIZED = False
_FILE_LOGGING_INITIALIZED = False
_DEBUG_FILE_LOGGERS: set[tuple[str, str]] = set()


def _debug_enabled(config: dict[str, Any] | None) -> bool:
    if not isinstance(config, dict):
        return False
    debug = config.get("debug")
    if isinstance(debug, dict):
        return debug.get("enable") is True
    return debug is True


def _debug_path(config: dict[str, Any] | None) -> Path:
    if isinstance(config, dict):
        configured: object = None
        debug = config.get("debug")
        if isinstance(debug, dict):
            configured = debug.get("path")
        if isinstance(configured, str) and configured.strip():
            return Path(os.path.expandvars(configured.strip()))
    return LOG_DIR


def _configure_bridge_file_logging(config: dict[str, Any] | None) -> None:
    global _BRIDGE_FILE_LOGGING_INITIALIZED
    if config is None or _BRIDGE_FILE_LOGGING_INITIALIZED:
        return

    log_dir = LOG_DIR
    if isinstance(config, dict):
        debug = config.get("debug")
        if isinstance(debug, dict):
            configured = debug.get("path")
            if isinstance(configured, str) and configured.strip():
                log_dir = Path(os.path.expandvars(configured.strip()))

    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "bridge.log", encoding="utf-8")
    file_handler.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(file_handler)
    _BRIDGE_FILE_LOGGING_INITIALIZED = True


def configure_logging(config: dict[str, Any] | None = None) -> None:
    global _LOGGING_INITIALIZED, _FILE_LOGGING_INITIALIZED
    root_logger = logging.getLogger()
    debug = _debug_enabled(config)
    level = "DEBUG" if debug else os.getenv("LOG_LEVEL", "INFO").upper()

    if _LOGGING_INITIALIZED:
        root_logger.setLevel(level)
    else:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
            stream=sys.stdout,
        )
        _LOGGING_INITIALIZED = True

    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())

    _configure_bridge_file_logging(config)

    if not debug or _FILE_LOGGING_INITIALIZED:
        return

    log_dir = _debug_path(config)
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_dir / "bridge-debug.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root_logger.addHandler(file_handler)
    _FILE_LOGGING_INITIALIZED = True


def configure_debug_file_logger(logger_name: str, config: dict[str, Any], filename: str) -> logging.Logger:
    log_dir = _debug_path(config)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / filename
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)

    handler_key = (logger_name, str(log_path.resolve()))
    if handler_key not in _DEBUG_FILE_LOGGERS:
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
        logger.addHandler(file_handler)
        _DEBUG_FILE_LOGGERS.add(handler_key)

    return logger


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)
