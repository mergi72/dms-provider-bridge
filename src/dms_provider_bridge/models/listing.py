from __future__ import annotations

from pydantic import BaseModel, Field

from dms_provider_bridge.models.item import DmsItem


class ListingResult(BaseModel):
    provider: str = Field(
        description="Legacy alias for connection. Kept for compatibility with WFX clients and older API consumers.",
    )
    connection: str | None = Field(
        default=None,
        description="Connection/mount name that produced this listing.",
    )
    path: str = Field(description="Listed path inside the connection.")
    total: int = Field(ge=0, description="Number of returned items.")
    items: list[DmsItem]

    def model_post_init(self, __context: object) -> None:
        if self.connection is None:
            self.connection = self.provider

