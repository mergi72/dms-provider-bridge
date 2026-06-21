from __future__ import annotations

from dms_provider_bridge.adapters.commander_api import parse_wfx_path
from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.core.config_loader import connection_driver_name
from dms_provider_bridge.services.connection_runtime_service import get_connection_runtime


def _normalize_connection_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().rstrip(":")
    return normalized or None


def _effective_connection_name(legacy_provider_name: str | None = None, connection_name: str | None = None) -> str | None:
    legacy_name = _normalize_connection_name(legacy_provider_name)
    new_name = _normalize_connection_name(connection_name)
    if legacy_name and new_name and legacy_name != new_name and connection_driver_name(new_name) != legacy_name:
        raise ValueError(
            f"Connection mismatch: provider_name '{legacy_provider_name}' does not match connection_name '{connection_name}'."
        )
    return new_name or legacy_name


def list_connection_items(path: str, connection_name: str | None = None) -> ListingResult:
    resolved_path = path
    resolved_connection_name = _normalize_connection_name(connection_name)

    if resolved_connection_name is None and ":" in path:
        try:
            parsed = parse_wfx_path(path)
            resolved_connection_name = parsed.connection
            resolved_path = parsed.path
        except ValueError:
            pass

    connection_runtime = get_connection_runtime(resolved_connection_name)
    return connection_runtime.list_items(resolved_path)


def list_items(path: str, provider_name: str | None = None, *, connection_name: str | None = None) -> ListingResult:
    return list_connection_items(path, _effective_connection_name(provider_name, connection_name))

