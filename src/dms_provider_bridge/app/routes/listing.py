from __future__ import annotations

from fastapi import APIRouter, Query

from dms_provider_bridge.services.listing_service import list_items

router = APIRouter()


@router.get("")
def listing(
    path: str = Query(
        default="/",
        description="Connection path to list. Use connection:/path or / to list available connections.",
    ),
    connection: str | None = Query(
        default=None,
        description="Preferred connection/mount name.",
    ),
    provider: str | None = Query(
        default=None,
        description="Legacy alias for connection. Kept for compatibility with older clients.",
    ),
) -> dict:
    result = list_items(path=path, provider_name=provider, connection_name=connection)
    return result.model_dump()

