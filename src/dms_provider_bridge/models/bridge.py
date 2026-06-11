from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class BridgeAuthContext(BaseModel):
    mode: Literal["credentials", "winuser", "windows"]
    credential_id: str | None = None
    target: str | None = Field(
        default=None,
        description="Compatibility alias for provider auth target; mapped to credential_id for windows auth requests.",
    )
    username: str | None = None
    password: str | None = None
    token: str | None = None
    win_user: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_auth_mode(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        normalized = dict(data)
        if normalized.get("mode") == "windows":
            normalized["mode"] = "credentials"
            if not normalized.get("credential_id") and normalized.get("target"):
                normalized["credential_id"] = normalized.get("target")
        return normalized


class UploadVersioning(BaseModel):
    mode: Literal["version"] = Field(
        default="version",
        description="DMS versioning mode for providers that require explicit version choice.",
    )
    majorVersion: bool = Field(
        default=False,
        description="Provider-compatible major version flag. false creates a minor version, true creates a major version.",
    )
    comment: str | None = Field(
        default=None,
        description="Optional version comment sent to the DMS provider.",
    )


class WfxPathRequest(BaseModel):
    path: str = Field(
        min_length=0,
        description="Path in format provider:/path. Use / or an empty path to list available providers.",
    )
    auth: BridgeAuthContext | None = None


class WfxMoveRequest(BaseModel):
    source: str = Field(
        min_length=3,
        description="Source path in format provider:/path.",
    )
    destination: str = Field(
        min_length=3,
        description="Destination path in format provider:/path. Use the same provider prefix for same-provider operations.",
    )
    auth: BridgeAuthContext


class WfxUploadRequest(BaseModel):
    destination: str = Field(
        min_length=3,
        description="Destination folder or file path in format provider:/path.",
    )
    auth: BridgeAuthContext
    file_name: str = Field(min_length=1)
    content_base64: str | None = None
    source_path: str | None = None
    overwrite: bool = False
    versioning: UploadVersioning | None = None


class WfxShareUrlRequest(BaseModel):
    share_url: str = Field(min_length=10, description="Full provider share URL.")
    provider: str = Field(min_length=1, description="Provider key that supports this Share URL format.")


class WfxShareUrlBrowseRequest(BaseModel):
    share_url: str = Field(min_length=10, description="Full provider share URL.")
    auth: BridgeAuthContext
    provider: str = Field(min_length=1, description="Provider key that supports this Share URL format.")
    operation: Literal["list", "stat", "download", "copy", "move", "mkdir", "delete", "upload"] = "list"
    execute: bool = True
    provider_path_override: str | None = Field(
        default=None,
        description="Optional provider path override in /path format.",
    )
    destination_share_url: str | None = Field(default=None, description="Optional destination Share URL for copy/move.")
    destination_path_override: str | None = Field(
        default=None,
        description="Optional destination path override in /path format.",
    )
    file_name: str | None = Field(default=None, description="File name for upload operation")
    content_base64: str | None = Field(default=None, description="Inline file content for upload operation")
    overwrite: bool = False
    versioning: UploadVersioning | None = None


class WfxShareUrlValidateRequest(BaseModel):
    share_url: str = Field(min_length=10, description="Full provider share URL.")
    provider: str = Field(min_length=1, description="Provider key that supports this Share URL format.")
    operation: Literal["list", "stat", "download", "copy", "move", "mkdir", "delete", "upload"] = "list"
    provider_path_override: str | None = Field(
        default=None,
        description="Optional provider path override in /path format.",
    )
    destination_share_url: str | None = Field(default=None, description="Optional destination Share URL for copy/move/upload.")
    destination_path_override: str | None = Field(
        default=None,
        description="Optional destination path override in /path format.",
    )
    file_name: str | None = Field(default=None, description="File name for upload operation")


class WfxResponse(BaseModel):
    ok: bool
    error_code: int = 0
    message: str | None = None
    data: Any = None
    metadata: dict[str, Any] | None = None
