from __future__ import annotations

from dataclasses import dataclass


class WfxErrorCode:
    OK = 0
    NOT_SUPPORTED = 1
    NOT_FOUND = 2
    ACCESS_DENIED = 3
    BAD_PATH = 4
    INTERNAL_ERROR = 5


@dataclass(slots=True)
class ParsedWfxPath:
    connection: str
    path: str

    @property
    def provider(self) -> str:
        """Backward-compatible alias for older provider-named call sites."""
        return self.connection


def parse_wfx_path(raw_path: str) -> ParsedWfxPath:
    """Parse path in format connection:/absolute/path."""
    if not raw_path:
        raise ValueError("Path is empty.")

    prefix, sep, suffix = raw_path.partition(":")
    connection = prefix.strip().lower()
    if not sep or not connection:
        raise ValueError("Expected path format 'connection:/path'.")

    normalized = suffix.strip() or "/"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return ParsedWfxPath(connection=connection, path=normalized)


def build_wfx_path(connection: str, path: str) -> str:
    normalized = path if path.startswith("/") else f"/{path}"
    return f"{connection}:{normalized}"


def split_optional_wfx_path(path: str) -> tuple[str | None, str]:
    """Split connection:/path when present; leave local/plain paths untouched."""
    raw = path.strip()
    if not raw:
        return None, raw
    prefix, sep, suffix = raw.partition(":")
    if sep and len(prefix.strip()) > 1 and suffix.strip().replace("\\", "/").startswith("/"):
        parsed = parse_wfx_path(raw)
        return parsed.connection, parsed.path
    return None, raw


def map_commander_payload(payload: dict) -> dict:
    """Simple no-op mapper, kept for compatibility with planned TC/WFX wrapper."""
    return payload
