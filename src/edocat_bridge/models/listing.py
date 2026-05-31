from __future__ import annotations

from pydantic import BaseModel, Field

from edocat_bridge.models.item import DmsItem


class ListingResult(BaseModel):
    provider: str
    path: str
    total: int = Field(ge=0)
    items: list[DmsItem]
