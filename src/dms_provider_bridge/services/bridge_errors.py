from __future__ import annotations

from dataclasses import dataclass

from dms_provider_bridge.adapters.commander_api import WfxErrorCode
from dms_provider_bridge.core.errors import AuthenticationError, ProviderNotFoundError, VersionRequiredError
from dms_provider_bridge.services.bridge_transfer_ops import TransferPrecheckError


@dataclass(frozen=True, slots=True)
class BridgeError:
    code: int
    message: str
    metadata: dict | None = None


def map_exception(exc: Exception) -> BridgeError:
    if isinstance(exc, AuthenticationError):
        return BridgeError(WfxErrorCode.ACCESS_DENIED, str(exc))
    if isinstance(exc, ProviderNotFoundError):
        return BridgeError(WfxErrorCode.NOT_SUPPORTED, str(exc))
    if isinstance(exc, VersionRequiredError):
        return BridgeError(WfxErrorCode.ACCESS_DENIED, str(exc), exc.metadata)
    if isinstance(exc, TransferPrecheckError):
        return BridgeError(WfxErrorCode.INTERNAL_ERROR, str(exc))
    if isinstance(exc, ValueError):
        return BridgeError(WfxErrorCode.BAD_PATH, str(exc))
    return BridgeError(WfxErrorCode.INTERNAL_ERROR, str(exc))
