from __future__ import annotations

from urllib.parse import unquote, urlparse

from edocat_bridge.adapters.commander_api import WfxErrorCode, build_wfx_path, parse_wfx_path
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
        listing = provider.list_items(parsed.path, auth)
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
        item = provider.stat_item(parsed.path, auth)
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
        result = provider.make_dir(parsed.path, auth)
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
        result = provider.delete_item(parsed.path, auth)
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
        result = src_provider.rename_item(src.path, dst.path, auth)
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
        result = src_provider.copy_item(src.path, dst.path, auth)
        return _success(data=result.model_dump(), metadata=_metadata(src_provider, "copy"))
    except AuthenticationError as exc:
        return _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
    except ValueError as exc:
        return _failure(WfxErrorCode.BAD_PATH, str(exc))
    except ProviderNotFoundError as exc:
        return _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
    except Exception as exc:
        return _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))


def download_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    try:
        provider, parsed = _resolve(path)
        validate_bridge_auth(auth)
        result = provider.download_item(parsed.path, auth)
        return _success(data=result.model_dump(), metadata=_metadata(provider, "download"))
    except AuthenticationError as exc:
        return _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
    except ValueError as exc:
        return _failure(WfxErrorCode.BAD_PATH, str(exc))
    except ProviderNotFoundError as exc:
        return _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
    except Exception as exc:
        return _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))


def upload_path(destination: str, file_name: str, auth: BridgeAuthContext, content_base64: str | None = None, overwrite: bool = False) -> WfxResponse:
    try:
        provider, parsed = _resolve(destination)
        validate_bridge_auth(auth)
        result = provider.upload_item(parsed.path, file_name, content_base64=content_base64, overwrite=overwrite, auth=auth)
        return _success(data=result.model_dump(), metadata=_metadata(provider, "upload"))
    except AuthenticationError as exc:
        return _failure(WfxErrorCode.ACCESS_DENIED, str(exc))
    except ValueError as exc:
        return _failure(WfxErrorCode.BAD_PATH, str(exc))
    except ProviderNotFoundError as exc:
        return _failure(WfxErrorCode.NOT_SUPPORTED, str(exc))
    except Exception as exc:
        return _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))


def resolve_share_url(share_url: str, provider: str = "alfresco") -> WfxResponse:
    try:
        if provider != "alfresco":
            return _failure(WfxErrorCode.NOT_SUPPORTED, f"Unsupported provider for share URL: {provider}")

        parsed = urlparse(share_url)
        fragment = parsed.fragment or ""
        if not fragment:
            return _failure(WfxErrorCode.BAD_PATH, "Share URL must contain a hash path (fragment).")

        fragment_path = fragment.split("?", 1)[0].strip()
        if not fragment_path:
            return _failure(WfxErrorCode.BAD_PATH, "Share URL fragment path is empty.")

        normalized = unquote(fragment_path)
        normalized = normalized.replace("\\", "/")
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"

        wfx_path = build_wfx_path(provider, normalized)
        return _success(
            data={
                "provider": provider,
                "path": wfx_path,
                "share_path": normalized,
                "source_url": share_url,
            },
            metadata={"provider": provider, "operation": "resolve-share-url"},
        )
    except Exception as exc:
        return _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))


def browse_share_url(
    share_url: str,
    auth: BridgeAuthContext,
    provider: str = "alfresco",
    operation: str = "list",
    provider_path_override: str | None = None,
    destination_share_url: str | None = None,
    destination_path_override: str | None = None,
    file_name: str | None = None,
    content_base64: str | None = None,
    overwrite: bool = False,
) -> WfxResponse:
    resolved = resolve_share_url(share_url, provider)
    if not resolved.ok:
        return resolved

    if not isinstance(resolved.data, dict):
        return _failure(WfxErrorCode.INTERNAL_ERROR, "Resolved share URL payload has invalid format.")

    resolved_payload = dict(resolved.data)

    path = str(resolved_payload.get("path", ""))
    path_source = "share_url"
    if provider_path_override:
        normalized_override = unquote(provider_path_override).replace("\\", "/").strip()
        if not normalized_override:
            return _failure(WfxErrorCode.BAD_PATH, "provider_path_override is empty.")
        if not normalized_override.startswith("/"):
            normalized_override = f"/{normalized_override}"
        path = build_wfx_path(provider, normalized_override)
        resolved_payload["path"] = path
        resolved_payload["share_path"] = normalized_override
        path_source = "provider_path_override"

    if not path:
        return _failure(WfxErrorCode.BAD_PATH, "Resolved share URL does not contain a target path.")

    destination_path: str | None = None
    destination_source: str | None = None

    if operation == "list":
        response = list_path(path, auth)
    elif operation == "stat":
        response = stat_path(path, auth)
    elif operation == "download":
        response = download_path(path, auth)
    elif operation == "mkdir":
        response = mkdir_path(path, auth)
    elif operation == "delete":
        response = delete_path(path, auth)
    elif operation in {"copy", "rename"}:
        if destination_path_override:
            normalized_destination = unquote(destination_path_override).replace("\\", "/").strip()
            if not normalized_destination:
                return _failure(WfxErrorCode.BAD_PATH, "destination_path_override is empty.")
            if not normalized_destination.startswith("/"):
                normalized_destination = f"/{normalized_destination}"
            destination_path = build_wfx_path(provider, normalized_destination)
            destination_source = "destination_path_override"
        elif destination_share_url:
            destination_resolved = resolve_share_url(destination_share_url, provider)
            if not destination_resolved.ok:
                return destination_resolved
            if not isinstance(destination_resolved.data, dict):
                return _failure(WfxErrorCode.INTERNAL_ERROR, "Resolved destination share URL payload has invalid format.")
            destination_path = str(destination_resolved.data.get("path", ""))
            destination_source = "destination_share_url"
        else:
            return _failure(
                WfxErrorCode.BAD_PATH,
                "copy/rename requires destination_path_override or destination_share_url.",
            )

        if not destination_path:
            return _failure(WfxErrorCode.BAD_PATH, "Destination path is empty.")

        response = copy_path(path, destination_path, auth) if operation == "copy" else rename_path(path, destination_path, auth)
    elif operation == "upload":
        if not file_name:
            return _failure(WfxErrorCode.BAD_PATH, "upload requires file_name.")

        upload_destination_path = path
        upload_destination_source = path_source
        if destination_path_override:
            normalized_destination = unquote(destination_path_override).replace("\\", "/").strip()
            if not normalized_destination:
                return _failure(WfxErrorCode.BAD_PATH, "destination_path_override is empty.")
            if not normalized_destination.startswith("/"):
                normalized_destination = f"/{normalized_destination}"
            upload_destination_path = build_wfx_path(provider, normalized_destination)
            upload_destination_source = "destination_path_override"
        elif destination_share_url:
            destination_resolved = resolve_share_url(destination_share_url, provider)
            if not destination_resolved.ok:
                return destination_resolved
            if not isinstance(destination_resolved.data, dict):
                return _failure(WfxErrorCode.INTERNAL_ERROR, "Resolved destination share URL payload has invalid format.")
            upload_destination_path = str(destination_resolved.data.get("path", ""))
            upload_destination_source = "destination_share_url"

        if not upload_destination_path:
            return _failure(WfxErrorCode.BAD_PATH, "Upload destination path is empty.")

        response = upload_path(
            upload_destination_path,
            file_name,
            auth,
            content_base64=content_base64,
            overwrite=overwrite,
        )
        destination_path = upload_destination_path
        destination_source = upload_destination_source
    else:
        return _failure(WfxErrorCode.NOT_SUPPORTED, f"Unsupported operation for share URL browse: {operation}")

    if not response.ok:
        return response

    merged_data = {
        "resolved": resolved_payload,
        "path_source": path_source,
        "result": response.data,
    }
    if operation in {"copy", "rename", "upload"} and destination_path and destination_source:
        merged_data["destination"] = {
            "path": destination_path,
            "path_source": destination_source,
        }
    merged_meta = dict(response.metadata or {})
    merged_meta["operation"] = f"browse-share-url:{operation}"
    return _success(data=merged_data, metadata=merged_meta)
