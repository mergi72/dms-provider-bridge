from __future__ import annotations

from edocat_bridge.adapters.commander_api import parse_wfx_path
from edocat_bridge.models.listing import ListingResult
from edocat_bridge.services.provider_service import get_provider


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

    provider = get_provider(resolved_provider_name)
    return provider.list_items(resolved_path)
