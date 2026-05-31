from __future__ import annotations

from edocat_bridge.models.listing import ListingResult
from edocat_bridge.services.provider_service import get_provider


def list_items(path: str, provider_name: str | None = None) -> ListingResult:
    provider = get_provider(provider_name)
    return provider.list_items(path)
