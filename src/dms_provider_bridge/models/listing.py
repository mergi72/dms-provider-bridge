from __future__ import annotations

from pydantic import BaseModel, Field

from dms_provider_bridge.models.item import DmsItem


class ListingResult(BaseModel):
    provider: str
    connection: str | None = None
    path: str
    total: int = Field(ge=0)
    items: list[DmsItem]

    def model_post_init(self, __context: object) -> None:
        if self.connection is None:
            self.connection = self.provider

