from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from dms_provider_bridge.core.connection_aliases import mirror_connection_result_aliases
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

    @model_validator(mode="before")
    @classmethod
    def normalize_connection_alias(cls, data: object) -> object:
        if isinstance(data, dict):
            return mirror_connection_result_aliases(data)
        return data

    def model_post_init(self, __context: object) -> None:
        if self.connection is None:
            self.connection = self.provider

