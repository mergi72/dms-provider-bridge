from __future__ import annotations

from pydantic import BaseModel, Field

from dms_provider_bridge.models.item import DmsItem


class SearchResult(BaseModel):
    connection: str
    path: str
    query: str
    total: int = Field(ge=0)
    items: list[DmsItem]
    truncated: bool = False
