from __future__ import annotations

from pydantic import BaseModel


class OperationResult(BaseModel):
    success: bool
    operation: str
    provider: str
    source: str | None = None
    destination: str | None = None
    message: str | None = None
