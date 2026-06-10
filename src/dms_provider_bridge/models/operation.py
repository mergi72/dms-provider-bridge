from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class OperationResult(BaseModel):
    success: bool
    operation: str
    provider: str
    source: str | None = None
    destination: str | None = None
    message: str | None = None
    content_base64: str | None = None
    mime_type: str | None = None
    size: int | None = None
    metadata: dict[str, Any] | None = None
