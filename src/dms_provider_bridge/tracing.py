from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from collections.abc import Iterator
from uuid import UUID, uuid4


CORRELATION_HEADER = "X-VFS-Correlation-ID"
_CURRENT_ID: ContextVar[str] = ContextVar("vfs_correlation_id", default="-")


def normalize_correlation_id(value: str | None) -> str:
    if value:
        try:
            return str(UUID(value.strip()))
        except (ValueError, AttributeError):
            pass
    return str(uuid4())


def current_correlation_id() -> str:
    return _CURRENT_ID.get()


@contextmanager
def correlation_scope(value: str | None) -> Iterator[str]:
    correlation_id = normalize_correlation_id(value)
    token = _CURRENT_ID.set(correlation_id)
    try:
        yield correlation_id
    finally:
        _CURRENT_ID.reset(token)
