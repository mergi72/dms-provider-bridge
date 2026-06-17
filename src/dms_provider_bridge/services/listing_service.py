from __future__ import annotations

from dms_provider_bridge.adapters.commander_api import parse_wfx_path
from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.services.provider_service import get_connection_runtime


def list_items(path: str, provider_name: str | None = None) -> ListingResult:
    resolved_path = path
    resolved_provider_name = provider_name

    if provider_name is None and ":" in path:
        try:
            parsed = parse_wfx_path(path)
            resolved_provider_name = parsed.provider
            resolved_path = parsed.path
        except ValueError:
            pass

    provider = get_connection_runtime(resolved_provider_name)
    return provider.list_items(resolved_path)

