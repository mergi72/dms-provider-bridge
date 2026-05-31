from __future__ import annotations

from pydantic import BaseModel


class ProviderConfig(BaseModel):
    name: str
    enabled: bool = True
    endpoint: str | None = None
