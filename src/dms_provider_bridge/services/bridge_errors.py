from __future__ import annotations

from dataclasses import dataclass
from urllib.error import HTTPError

from dms_provider_bridge.adapters.commander_api import WfxErrorCode
from dms_provider_bridge.core.errors import AuthenticationError, ProviderNotFoundError, ProviderOperationError, VersionRequiredError
from dms_provider_bridge.services.bridge_transfer_ops import TransferPrecheckError


@dataclass(frozen=True, slots=True)
class BridgeError:
    code: int
    message: str
    metadata: dict | None = None


def _upstream_status_code(exc: Exception) -> int | None:
    current: BaseException | None = exc
    while current is not None:
        status_code = getattr(current, "status_code", None)
        if isinstance(status_code, int) and status_code > 0:
            return status_code
        if isinstance(current, HTTPError):
            return int(current.code)
        current = current.__cause__
    return None


def _upstream_metadata(exc: Exception) -> dict | None:
    status_code = _upstream_status_code(exc)
    if status_code is None:
        return None
    return {"upstream_status_code": status_code}


def map_exception(exc: Exception) -> BridgeError:
    if isinstance(exc, AuthenticationError):
        return BridgeError(WfxErrorCode.ACCESS_DENIED, str(exc), _upstream_metadata(exc))
    if isinstance(exc, ProviderNotFoundError):
        return BridgeError(WfxErrorCode.NOT_SUPPORTED, str(exc))
    if isinstance(exc, VersionRequiredError):
        return BridgeError(WfxErrorCode.ACCESS_DENIED, str(exc), exc.metadata)
    if isinstance(exc, ProviderOperationError):
        return BridgeError(WfxErrorCode.INTERNAL_ERROR, str(exc), _upstream_metadata(exc))
    if isinstance(exc, TransferPrecheckError):
        return BridgeError(WfxErrorCode.INTERNAL_ERROR, str(exc))
    if isinstance(exc, ValueError):
        return BridgeError(WfxErrorCode.BAD_PATH, str(exc))
    return BridgeError(WfxErrorCode.INTERNAL_ERROR, str(exc))
