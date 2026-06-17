from __future__ import annotations

from dms_provider_bridge.adapters.commander_api import parse_wfx_path
from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.services.provider_service import get_connection_runtime


def _effective_connection_name(provider_name: str | None = None, connection_name: str | None = None) -> str | None:
    if provider_name and connection_name and provider_name.strip().lower().rstrip(":") != connection_name.strip().lower().rstrip(":"):
        raise ValueError(
            f"Connection mismatch: provider_name '{provider_name}' does not match connection_name '{connection_name}'."
        )
    return connection_name or provider_name


def list_items(path: str, provider_name: str | None = None, *, connection_name: str | None = None) -> ListingResult:
    resolved_path = path
    resolved_connection_name = _effective_connection_name(provider_name, connection_name)

    if resolved_connection_name is None and ":" in path:
        try:
            parsed = parse_wfx_path(path)
            resolved_connection_name = parsed.connection
            resolved_path = parsed.path
        except ValueError:
            pass

    provider = get_connection_runtime(resolved_connection_name)
    return provider.list_items(resolved_path)

