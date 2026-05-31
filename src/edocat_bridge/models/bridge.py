from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel, Field


class BridgeAuthContext(BaseModel):
    mode: Literal["credentials", "winuser"]
    credential_id: str | None = None
    username: str | None = None
    password: str | None = None
    token: str | None = None
    win_user: str | None = None


class WfxPathRequest(BaseModel):
    path: str = Field(min_length=3, description="Path in format provider:/path")
    auth: BridgeAuthContext


class WfxMoveRequest(BaseModel):
    source: str = Field(min_length=3, description="Source path in format provider:/path")
    destination: str = Field(min_length=3, description="Destination path in format provider:/path")
    auth: BridgeAuthContext


class WfxResponse(BaseModel):
    ok: bool
    error_code: int = 0
    message: str | None = None
    data: Any = None
    metadata: dict[str, Any] | None = None
