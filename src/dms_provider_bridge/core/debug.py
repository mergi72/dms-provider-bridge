from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dms_provider_bridge.core.paths import LOG_DIR

_DEBUG_FILE_LOGGERS: set[tuple[str, str]] = set()


def debug_enabled(config: dict[str, Any] | None) -> bool:
    if not isinstance(config, dict):
        return False
    debug = config.get("debug")
    if isinstance(debug, dict):
        return debug.get("enable") is True
    return debug is True


def debug_path(config: dict[str, Any] | None) -> Path:
    if isinstance(config, dict):
        debug = config.get("debug")
        if isinstance(debug, dict):
            configured = debug.get("path")
            if isinstance(configured, str) and configured.strip():
                return Path(os.path.expandvars(configured.strip()))
    return LOG_DIR


def configure_debug_file_logger(logger_name: str, config: dict[str, Any], filename: str) -> logging.Logger:
    log_dir = debug_path(config)
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


def connection_debug_logger(connection_name: str, config: dict[str, Any]) -> logging.Logger:
    logger_name = f"dms_provider_bridge.connections.{connection_name}"
    if not debug_enabled(config):
        return logging.getLogger(logger_name)
    return configure_debug_file_logger(logger_name, config, f"{connection_name}-debug.log")


def provider_debug_logger(provider_name: str, config: dict[str, Any]) -> logging.Logger:
    """Backward-compatible alias for connection debug logging."""
    return connection_debug_logger(provider_name, config)


def log_connection_operation_start(
    logger: logging.Logger,
    connection_name: str,
    operation: str,
    path: str | None = None,
    **fields: object,
) -> float:
    started = time.perf_counter()
    _log_connection_operation(logger, "connection_operation_start", connection_name, operation, path, None, None, fields)
    return started


def log_provider_operation_start(
    logger: logging.Logger,
    provider_name: str,
    operation: str,
    path: str | None = None,
    **fields: object,
) -> float:
    """Backward-compatible alias for connection operation logging."""
    return log_connection_operation_start(logger, provider_name, operation, path, **fields)


def log_connection_operation_done(
    logger: logging.Logger,
    connection_name: str,
    operation: str,
    started: float,
    path: str | None = None,
    **fields: object,
) -> None:
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    _log_connection_operation(logger, "connection_operation_done", connection_name, operation, path, "ok", elapsed_ms, fields)


def log_provider_operation_done(
    logger: logging.Logger,
    provider_name: str,
    operation: str,
    started: float,
    path: str | None = None,
    **fields: object,
) -> None:
    """Backward-compatible alias for connection operation logging."""
    log_connection_operation_done(logger, provider_name, operation, started, path, **fields)


def log_connection_operation_failed(
    logger: logging.Logger,
    connection_name: str,
    operation: str,
    started: float,
    path: str | None = None,
    error: BaseException | str | None = None,
    **fields: object,
) -> None:
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    if error is not None:
        fields = dict(fields)
        fields["error"] = str(error)
    _log_connection_operation(logger, "connection_operation_failed", connection_name, operation, path, "failed", elapsed_ms, fields)


def log_provider_operation_failed(
    logger: logging.Logger,
    provider_name: str,
    operation: str,
    started: float,
    path: str | None = None,
    error: BaseException | str | None = None,
    **fields: object,
) -> None:
    """Backward-compatible alias for connection operation logging."""
    log_connection_operation_failed(logger, provider_name, operation, started, path, error=error, **fields)


def debug_connection_operation(
    logger: logging.Logger,
    connection_name: str,
    operation: str,
    path: str | None,
    func: Callable[[], Any],
) -> Any:
    started = log_connection_operation_start(logger, connection_name, operation, path)
    try:
        result = func()
    except Exception as exc:
        log_connection_operation_failed(logger, connection_name, operation, started, path, error=exc)
        raise
    log_connection_operation_done(logger, connection_name, operation, started, path)
    return result


def debug_operation(
    logger: logging.Logger,
    provider_name: str,
    operation: str,
    path: str | None,
    func: Callable[[], Any],
) -> Any:
    """Backward-compatible alias for connection operation debug wrapping."""
    started = log_connection_operation_start(logger, provider_name, operation, path)
    try:
        result = func()
    except Exception as exc:
        log_connection_operation_failed(logger, provider_name, operation, started, path, error=exc)
        raise
    log_connection_operation_done(logger, provider_name, operation, started, path)
    return result


def _log_connection_operation(
    logger: logging.Logger,
    event: str,
    connection_name: str,
    operation: str,
    path: str | None,
    status: str | None,
    elapsed_ms: int | None,
    fields: dict[str, object],
) -> None:
    if not logger.isEnabledFor(logging.DEBUG):
        return

    parts: list[str] = [event]
    parts.extend([f"connection={connection_name}", f"provider={connection_name}", f"operation={operation}"])
    if path is not None:
        parts.append(f"path={path}")
    if status is not None:
        parts.append(f"status={status}")
    if elapsed_ms is not None:
        parts.append(f"elapsed_ms={elapsed_ms}")
    for key, value in fields.items():
        if value is not None:
            parts.append(f"{key}={value}")
    logger.debug(" ".join(parts))
