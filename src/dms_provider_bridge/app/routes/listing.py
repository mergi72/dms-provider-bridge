from __future__ import annotations

from fastapi import APIRouter, Query

from dms_provider_bridge.services.listing_service import list_items

router = APIRouter()


@router.get("")
def listing(path: str = Query(default="/"), provider: str | None = None, connection: str | None = None) -> dict:
    result = list_items(path=path, provider_name=provider, connection_name=connection)
    return result.model_dump()

