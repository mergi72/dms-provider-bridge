from __future__ import annotations

from edocat_bridge.adapters.commander_api import WfxErrorCode, parse_wfx_path
from edocat_bridge.core.errors import AuthenticationError, ProviderNotFoundError
from edocat_bridge.models.bridge import BridgeAuthContext, WfxResponse
from edocat_bridge.services.auth_service import validate_bridge_auth
from edocat_bridge.services.provider_service import get_provider


def _success(data: object = None, message: str | None = None, metadata: dict | None = None) -> WfxResponse:
    return WfxResponse(ok=True, error_code=WfxErrorCode.OK, message=message, data=data, metadata=metadata)


def _failure(code: int, message: str) -> WfxResponse:
    return WfxResponse(ok=False, error_code=code, message=message, data=None)


def _resolve(path: str):
    parsed = parse_wfx_path(path)
    provider = get_provider(parsed.provider)
    return provider, parsed


def _metadata(provider, operation: str) -> dict[str, str | None]:
    return {
        "provider": provider.name,
        "upstream_auth_scheme": provider.upstream_auth_scheme,
        "upstream_endpoint": provider.bridge_endpoint_for(operation),
    }


def list_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    try:
        provider, parsed = _resolve(path)
        validate_bridge_auth(auth)
        listing = provider.list_items(parsed.path)
        return _success(data=listing.model_dump(), metadata=_metadata(provider, "list"))
    except AuthenticationError as exc:
        return _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
    except ValueError as exc:
        return _failure(WfxErrorCode.BAD_PATH, str(exc))
    except ProviderNotFoundError as exc:
        return _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
    except Exception as exc:
        return _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))


def stat_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    try:
        provider, parsed = _resolve(path)
        validate_bridge_auth(auth)
        item = provider.stat_item(parsed.path)
        if item is None:
            return _failure(WfxErrorCode.NOT_FOUND, f"Path not found: {path}")
        return _success(data=item.model_dump(), metadata=_metadata(provider, "stat"))
    except AuthenticationError as exc:
        return _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
    except ValueError as exc:
        return _failure(WfxErrorCode.BAD_PATH, str(exc))
    except ProviderNotFoundError as exc:
        return _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
    except Exception as exc:
        return _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))


def mkdir_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    try:
        provider, parsed = _resolve(path)
        validate_bridge_auth(auth)
        result = provider.make_dir(parsed.path)
        return _success(data=result.model_dump(), metadata=_metadata(provider, "mkdir"))
    except AuthenticationError as exc:
        return _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
    except ValueError as exc:
        return _failure(WfxErrorCode.BAD_PATH, str(exc))
    except ProviderNotFoundError as exc:
        return _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
    except Exception as exc:
        return _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))


def delete_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    try:
        provider, parsed = _resolve(path)
        validate_bridge_auth(auth)
        result = provider.delete_item(parsed.path)
        return _success(data=result.model_dump(), metadata=_metadata(provider, "delete"))
    except AuthenticationError as exc:
        return _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
    except ValueError as exc:
        return _failure(WfxErrorCode.BAD_PATH, str(exc))
    except ProviderNotFoundError as exc:
        return _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
    except Exception as exc:
        return _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))


def rename_path(source: str, destination: str, auth: BridgeAuthContext) -> WfxResponse:
    try:
        src_provider, src = _resolve(source)
        dst_provider, dst = _resolve(destination)
        validate_bridge_auth(auth)
        if src_provider.name != dst_provider.name:
            return _failure(WfxErrorCode.NOT_SUPPORTED, "Cross-provider rename is not supported.")
        result = src_provider.rename_item(src.path, dst.path)
        return _success(data=result.model_dump(), metadata=_metadata(src_provider, "rename"))
    except AuthenticationError as exc:
        return _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
    except ValueError as exc:
        return _failure(WfxErrorCode.BAD_PATH, str(exc))
    except ProviderNotFoundError as exc:
        return _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
    except Exception as exc:
        return _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))


def copy_path(source: str, destination: str, auth: BridgeAuthContext) -> WfxResponse:
    try:
        src_provider, src = _resolve(source)
        dst_provider, dst = _resolve(destination)
        validate_bridge_auth(auth)
        if src_provider.name != dst_provider.name:
            return _failure(WfxErrorCode.NOT_SUPPORTED, "Cross-provider copy is not supported.")
        result = src_provider.copy_item(src.path, dst.path)
        return _success(data=result.model_dump(), metadata=_metadata(src_provider, "copy"))
    except AuthenticationError as exc:
        return _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
    except ValueError as exc:
        return _failure(WfxErrorCode.BAD_PATH, str(exc))
    except ProviderNotFoundError as exc:
        return _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
    except Exception as exc:
        return _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))
