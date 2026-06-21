from __future__ import annotations

from dms_provider_bridge.adapters.commander_api import parse_wfx_path
from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.core.config_loader import connection_driver_name
from dms_provider_bridge.core.connection_aliases import normalize_connection_name, resolve_connection_alias
from dms_provider_bridge.services.connection_runtime_service import get_connection_runtime


def list_connection_items(path: str, connection_name: str | None = None) -> ListingResult:
    """List items through the connection-first runtime API."""
    resolved_path = path
    resolved_connection_name = normalize_connection_name(connection_name)

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
    """Compatibility wrapper.

    ``connection_name`` is the preferred argument. ``provider_name`` remains a
    legacy alias for older API adapters and tests during the 0.9.x transition.
    """
    return list_connection_items(
        path,
        resolve_connection_alias(provider_name, connection_name, connection_driver_name_fn=connection_driver_name),
    )

