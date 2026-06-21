from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from dms_provider_bridge.core.connection_aliases import mirror_connection_result_aliases


class OperationResult(BaseModel):
    success: bool
    operation: str
    provider: str = Field(
        description="Legacy alias for connection. Kept for compatibility with WFX clients and older API consumers.",
    )
    connection: str | None = Field(
        default=None,
        description="Connection/mount name that handled the operation.",
    )
    source: str | None = None
    destination: str | None = None
    message: str | None = None
    content_base64: str | None = None
    mime_type: str | None = None
    size: int | None = None
    metadata: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_connection_alias(cls, data: object) -> object:
        if isinstance(data, dict):
            return mirror_connection_result_aliases(data)
        return data

    def model_post_init(self, __context: object) -> None:
        if self.connection is None:
            self.connection = self.provider
