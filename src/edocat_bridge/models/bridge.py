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


class WfxUploadRequest(BaseModel):
    destination: str = Field(min_length=3, description="Destination folder or file path in format provider:/path")
    auth: BridgeAuthContext
    file_name: str = Field(min_length=1)
    content_base64: str | None = None
    overwrite: bool = False


class WfxShareUrlRequest(BaseModel):
    share_url: str = Field(min_length=10, description="Full eDoCat/Alfresco Share URL")
    provider: Literal["alfresco"] = "alfresco"


class WfxShareUrlBrowseRequest(BaseModel):
    share_url: str = Field(min_length=10, description="Full eDoCat/Alfresco Share URL")
    auth: BridgeAuthContext
    provider: Literal["alfresco"] = "alfresco"
    operation: Literal["list", "stat", "download"] = "list"
    provider_path_override: str | None = Field(default=None, description="Optional provider path override in /path format")


class WfxResponse(BaseModel):
    ok: bool
    error_code: int = 0
    message: str | None = None
    data: Any = None
    metadata: dict[str, Any] | None = None
