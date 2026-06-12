from __future__ import annotations

import base64
import os
import tempfile
import time

from dms_provider_bridge.adapters.commander_api import WfxErrorCode, build_wfx_path, parse_wfx_path
from dms_provider_bridge.core.logging import get_logger
from dms_provider_bridge.core.errors import ProviderNotFoundError
from dms_provider_bridge.models.bridge import BridgeAuthContext, WfxResponse
from dms_provider_bridge.models.item import DmsItem
from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.services.auth_service import validate_bridge_auth
from dms_provider_bridge.services.bridge_errors import map_exception
from dms_provider_bridge.services.provider_service import get_default_provider_name, get_provider, list_registered_providers
from dms_provider_bridge.services.bridge_transfer_ops import estimated_binary_size_from_base64, max_inline_upload_bytes, upload_with_preflight


_LOGGER = get_logger(__name__)


def _success(data: object = None, message: str | None = None, metadata: dict | None = None) -> WfxResponse:
    return WfxResponse(ok=True, error_code=WfxErrorCode.OK, message=message, data=data, metadata=metadata)


def _failure(code: int, message: str, metadata: dict | None = None) -> WfxResponse:
    return WfxResponse(ok=False, error_code=code, message=message, data=None, metadata=metadata)


def _failure_from_exception(exc: Exception) -> WfxResponse:
    mapped = map_exception(exc)
    return _failure(mapped.code, mapped.message, mapped.metadata)


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


def _deduplicate_repeated_leaf(path: str) -> str | None:
    normalized = (path or "").strip()
    if not normalized:
        return None

    if not normalized.startswith("/"):
        normalized = f"/{normalized}"

    parts = [segment for segment in normalized.split("/") if segment]
    if len(parts) < 2:
        return None
    if parts[-1] != parts[-2]:
        return None

    return "/" + "/".join(parts[:-1])


def _is_provider_root_path(path: str | None) -> bool:
    normalized = (path or "").strip().replace("\\", "/")
    return normalized in {"", "/"}


def _split_parent_and_name(path: str) -> tuple[str, str]:
    normalized = (path or "").strip().replace("\\", "/") or "/"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    normalized = normalized.rstrip("/") or "/"
    if normalized == "/":
        return "/", ""
    parent, name = normalized.rsplit("/", 1)
    return parent or "/", name


def _write_base64_to_temp_file(content_base64: str) -> str:
    payload = content_base64.strip()
    handle = tempfile.NamedTemporaryFile(prefix="dms-provider-transfer-", suffix=".bin", delete=False)
    try:
        chunk_chars = 4 * 1024 * 1024
        for offset in range(0, len(payload), chunk_chars):
            chunk = payload[offset : offset + chunk_chars]
            handle.write(base64.b64decode(chunk))
        return handle.name
    except Exception:
        temp_path = handle.name
        handle.close()
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
    finally:
        handle.close()


def _upload_downloaded_content(dst_provider, target_folder: str, file_name: str, auth: BridgeAuthContext, content_base64: str):
    payload_size = estimated_binary_size_from_base64(content_base64)
    if payload_size <= max_inline_upload_bytes(dst_provider):
        return upload_with_preflight(
            dst_provider,
            target_folder,
            file_name,
            auth,
            content_base64=content_base64,
            overwrite=False,
        )

    temp_path = _write_base64_to_temp_file(content_base64)
    try:
        return upload_with_preflight(
            dst_provider,
            target_folder,
            file_name,
            auth,
            source_path=temp_path,
            overwrite=False,
        )
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            _LOGGER.warning("transfer_temp_file_cleanup_failed path=%s", temp_path)


def _operation_failure_message(operation: str, result) -> str:
    detail = getattr(result, "message", None) or getattr(result, "error", None) or "provider returned an unsuccessful result"
    return f"Cross-provider {operation} failed: {detail}."


def _copy_auth(auth: BridgeAuthContext) -> BridgeAuthContext:
    return auth.model_copy(deep=True)


def _validated_auth(auth: BridgeAuthContext) -> BridgeAuthContext:
    auth_copy = _copy_auth(auth)
    validate_bridge_auth(auth_copy)
    return auth_copy


def _provider_root_listing() -> ListingResult:
    providers = list_registered_providers()
    items = [
        DmsItem(
            id=provider_name,
            name=provider_name,
            path=build_wfx_path(provider_name, "/"),
            is_folder=True,
            mime_type="application/x-dms-provider",
        )
        for provider_name in providers
    ]
    return ListingResult(provider="bridge", path="/", total=len(items), items=items)


def _default_provider_name_or_none() -> str | None:
    try:
        return get_default_provider_name()
    except Exception as exc:
        _LOGGER.warning("default_provider_unavailable error=%s", exc)
        return None


def _provider_capabilities(provider) -> dict[str, bool]:
    method_by_operation = {
        "list": "list_items",
        "stat": "stat_item",
        "download": "download_item",
        "upload": "upload_item",
        "mkdir": "make_dir",
        "delete": "delete_item",
        "rename": "rename_item",
        "copy": "copy_item",
    }
    return {
        operation: callable(getattr(provider, method_name, None))
        for operation, method_name in method_by_operation.items()
    }


def _versioning_payload(versioning: object) -> dict | None:
    if versioning is None:
        return None
    if hasattr(versioning, "model_dump"):
        dumped = versioning.model_dump(exclude_none=True)
        return dumped if isinstance(dumped, dict) else None
    return versioning if isinstance(versioning, dict) else None


def _provider_versioning(provider) -> dict[str, object]:
    return provider.versioning_capabilities()


def _provider_auth_requirements(provider) -> dict[str, object]:
    config = getattr(provider, "config", {})
    credentials = config.get("credentials") if isinstance(config, dict) else None
    auth: dict[str, object] = {}
    if isinstance(credentials, dict):
        mode = str(credentials.get("mode") or "").strip() or "credentials"
        auth["mode"] = mode
        for key in ("target", "targetBase"):
            value = credentials.get(key)
            if isinstance(value, str) and value.strip():
                auth[key] = value
        required = credentials.get("required")
        auth["required"] = bool(required) if isinstance(required, bool) else mode.lower() != "none"
        return auth

    if getattr(provider, "upstream_auth_scheme", "unknown") == "none":
        return {"mode": "none", "required": False}
    return {"mode": "credentials", "required": True}


def _log_and_return(
    operation: str,
    provider: str | None,
    path: str,
    started_at: float,
    response: WfxResponse,
    error: str | None = None,
) -> WfxResponse:
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    provider_value = provider or "-"
    error_value = error or response.message or ""
    level_method = _LOGGER.info if response.ok else _LOGGER.warning
    level_method(
        "bridge_operation operation=%s provider=%s path=%s error=%s duration_ms=%d",
        operation,
        provider_value,
        path,
        error_value,
        duration_ms,
    )
    return response


def providers_path() -> WfxResponse:
    started_at = time.perf_counter()
    providers = list_registered_providers()
    default_provider = _default_provider_name_or_none()
    response = _success(
        data={
            "providers": providers,
            "default_provider": default_provider,
        },
        metadata={"operation": "providers"},
    )
    return _log_and_return("providers", None, "/", started_at, response)


def provider_detail_path(provider_name: str) -> WfxResponse:
    started_at = time.perf_counter()
    try:
        provider = get_provider(provider_name)
        response = _success(
            data={
                "name": provider.name,
                "enabled": provider.name in list_registered_providers(),
                "auth": _provider_auth_requirements(provider),
                "capabilities": _provider_capabilities(provider),
                "versioning": _provider_versioning(provider),
            },
            metadata={"operation": "provider_detail", "provider": provider.name},
        )
        return _log_and_return("provider_detail", provider.name, "/", started_at, response)
    except ProviderNotFoundError as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("provider_detail", provider_name, "/", started_at, response, str(exc))


def list_path(path: str, auth: BridgeAuthContext | None) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    resolved_path = path
    try:
        if _is_provider_root_path(path):
            response = _success(
                data=_provider_root_listing().model_dump(),
                metadata={
                    "operation": "list",
                    "provider_root": True,
                    "providers": list_registered_providers(),
                    "default_provider": _default_provider_name_or_none(),
                },
            )
            return _log_and_return("list", "bridge", "/", started_at, response)
        if auth is None:
            response = _failure(WfxErrorCode.ACCESS_DENIED, "Authentication is required for provider paths.")
            return _log_and_return("list", provider_name, resolved_path, started_at, response, response.message)
        provider, parsed = _resolve(path)
        provider_name = provider.name
        resolved_path = parsed.path
        validate_bridge_auth(auth)
        listing = provider.list_items(parsed.path, auth)
        response = _success(data=listing.model_dump(), metadata=_metadata(provider, "list"))
        return _log_and_return("list", provider_name, resolved_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("list", provider_name, resolved_path, started_at, response, str(exc))


def stat_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    resolved_path = path
    try:
        provider, parsed = _resolve(path)
        provider_name = provider.name
        resolved_path = parsed.path
        validate_bridge_auth(auth)
        item = provider.stat_item(parsed.path, auth)
        if item is None:
            deduplicated_path = _deduplicate_repeated_leaf(parsed.path)
            if deduplicated_path and deduplicated_path != parsed.path:
                item = provider.stat_item(deduplicated_path, auth)
                if item is not None:
                    resolved_path = deduplicated_path
                    response = _success(data=item.model_dump(), metadata=_metadata(provider, "stat"))
                    return _log_and_return("stat", provider_name, resolved_path, started_at, response)

            response = _failure(WfxErrorCode.NOT_FOUND, f"Path not found: {path}")
            return _log_and_return("stat", provider_name, resolved_path, started_at, response, response.message)
        response = _success(data=item.model_dump(), metadata=_metadata(provider, "stat"))
        return _log_and_return("stat", provider_name, resolved_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("stat", provider_name, resolved_path, started_at, response, str(exc))


def mkdir_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    resolved_path = path
    try:
        provider, parsed = _resolve(path)
        provider_name = provider.name
        resolved_path = parsed.path
        validate_bridge_auth(auth)
        result = provider.make_dir(parsed.path, auth)
        response = _success(data=result.model_dump(), metadata=_metadata(provider, "mkdir"))
        return _log_and_return("mkdir", provider_name, resolved_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("mkdir", provider_name, resolved_path, started_at, response, str(exc))


def delete_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    resolved_path = path
    try:
        provider, parsed = _resolve(path)
        provider_name = provider.name
        resolved_path = parsed.path
        validate_bridge_auth(auth)
        result = provider.delete_item(parsed.path, auth)
        response = _success(data=result.model_dump(), metadata=_metadata(provider, "delete"))
        return _log_and_return("delete", provider_name, resolved_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("delete", provider_name, resolved_path, started_at, response, str(exc))


def rename_path(
    source: str,
    destination: str,
    auth: BridgeAuthContext,
    source_auth: BridgeAuthContext | None = None,
    destination_auth: BridgeAuthContext | None = None,
) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    operation_path = f"{source} -> {destination}"
    try:
        src_provider, src = _resolve(source)
        dst_provider, dst = _resolve(destination)
        provider_name = src_provider.name
        operation_path = f"{src.path} -> {dst.path}"
        src_auth = _validated_auth(source_auth or auth)
        if src_provider.name != dst_provider.name:
            dst_auth = _validated_auth(destination_auth or auth)
            target_folder, file_name = _split_parent_and_name(dst.path)
            if not file_name:
                response = _failure(WfxErrorCode.BAD_PATH, "Cross-provider move requires a destination file name.")
                return _log_and_return("rename", provider_name, operation_path, started_at, response, response.message)
            download_result = src_provider.download_item(src.path, src_auth)
            if not download_result.success:
                response = _failure(WfxErrorCode.INTERNAL_ERROR, _operation_failure_message("move download", download_result))
                return _log_and_return("rename", provider_name, operation_path, started_at, response, response.message)
            if not download_result.content_base64:
                response = _failure(WfxErrorCode.INTERNAL_ERROR, "Cross-provider move failed: source download returned no content.")
                return _log_and_return("rename", provider_name, operation_path, started_at, response, response.message)
            upload_result = _upload_downloaded_content(dst_provider, target_folder, file_name, dst_auth, download_result.content_base64)
            if not upload_result.success:
                response = _failure(WfxErrorCode.INTERNAL_ERROR, _operation_failure_message("move upload", upload_result))
                return _log_and_return("rename", provider_name, operation_path, started_at, response, response.message)
            delete_result = src_provider.delete_item(src.path, src_auth)
            response = _success(
                data=upload_result.model_dump(),
                metadata={
                    "operation": "rename",
                    "transfer": "download-upload-delete",
                    "source_provider": src_provider.name,
                    "destination_provider": dst_provider.name,
                    "delete": delete_result.model_dump(),
                },
            )
            return _log_and_return("rename", provider_name, operation_path, started_at, response)
        result = src_provider.rename_item(src.path, dst.path, src_auth)
        response = _success(data=result.model_dump(), metadata=_metadata(src_provider, "rename"))
        return _log_and_return("rename", provider_name, operation_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("rename", provider_name, operation_path, started_at, response, str(exc))


def copy_path(
    source: str,
    destination: str,
    auth: BridgeAuthContext,
    source_auth: BridgeAuthContext | None = None,
    destination_auth: BridgeAuthContext | None = None,
) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    operation_path = f"{source} -> {destination}"
    try:
        src_provider, src = _resolve(source)
        dst_provider, dst = _resolve(destination)
        provider_name = f"{src_provider.name}->{dst_provider.name}"
        operation_path = f"{src.path} -> {dst.path}"
        src_auth = _validated_auth(source_auth or auth)
        if src_provider.name == dst_provider.name:
            result = src_provider.copy_item(src.path, dst.path, src_auth)
            response = _success(data=result.model_dump(), metadata=_metadata(src_provider, "copy"))
            return _log_and_return("copy", provider_name, operation_path, started_at, response)

        dst_auth = _validated_auth(destination_auth or auth)
        target_folder, file_name = _split_parent_and_name(dst.path)
        if not file_name:
            response = _failure(WfxErrorCode.BAD_PATH, "Cross-provider copy requires a destination file name.")
            return _log_and_return("copy", provider_name, operation_path, started_at, response, response.message)
        download_result = src_provider.download_item(src.path, src_auth)
        if not download_result.success:
            response = _failure(WfxErrorCode.INTERNAL_ERROR, _operation_failure_message("copy download", download_result))
            return _log_and_return("copy", provider_name, operation_path, started_at, response, response.message)
        if not download_result.content_base64:
            response = _failure(WfxErrorCode.INTERNAL_ERROR, "Cross-provider copy failed: source download returned no content.")
            return _log_and_return("copy", provider_name, operation_path, started_at, response, response.message)
        upload_result = _upload_downloaded_content(dst_provider, target_folder, file_name, dst_auth, download_result.content_base64)
        if not upload_result.success:
            response = _failure(WfxErrorCode.INTERNAL_ERROR, _operation_failure_message("copy upload", upload_result))
            return _log_and_return("copy", provider_name, operation_path, started_at, response, response.message)
        response = _success(
            data=upload_result.model_dump(),
            metadata={
                "operation": "copy",
                "transfer": "download-upload",
                "source_provider": src_provider.name,
                "destination_provider": dst_provider.name,
            },
        )
        return _log_and_return("copy", provider_name, operation_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("copy", provider_name, operation_path, started_at, response, str(exc))


def download_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    resolved_path = path
    try:
        provider, parsed = _resolve(path)
        provider_name = provider.name
        resolved_path = parsed.path
        validate_bridge_auth(auth)
        result = provider.download_item(parsed.path, auth)
        response = _success(data=result.model_dump(), metadata=_metadata(provider, "download"))
        return _log_and_return("download", provider_name, resolved_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("download", provider_name, resolved_path, started_at, response, str(exc))


def open_download_stream(path: str, auth: BridgeAuthContext) -> WfxResponse | None:
    started_at = time.perf_counter()
    provider_name: str | None = None
    resolved_path = path
    try:
        provider, parsed = _resolve(path)
        provider_name = provider.name
        resolved_path = parsed.path
        stream_item = getattr(provider, "stream_item", None)
        if not callable(stream_item):
            return None
        validate_bridge_auth(auth)
        result = stream_item(parsed.path, auth)
        response = _success(data=result, metadata=_metadata(provider, "download"))
        return _log_and_return("download_raw_stream", provider_name, resolved_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("download_raw_stream", provider_name, resolved_path, started_at, response, str(exc))


def upload_path(destination: str, file_name: str, auth: BridgeAuthContext, content_base64: str | None = None, source_path: str | None = None, overwrite: bool = False, versioning: dict | None = None) -> WfxResponse:
    started_at = time.perf_counter()
    provider_name: str | None = None
    resolved_path = destination
    try:
        provider, parsed = _resolve(destination)
        provider_name = provider.name
        resolved_path = parsed.path
        validate_bridge_auth(auth)
        try:
            result = upload_with_preflight(provider, parsed.path, file_name, auth, content_base64=content_base64, source_path=source_path, overwrite=overwrite, versioning=_versioning_payload(versioning))
        except Exception as exc:
            response = _failure_from_exception(exc)
            return _log_and_return("upload", provider_name, resolved_path, started_at, response, str(exc))
        response = _success(data=result.model_dump(), metadata=_metadata(provider, "upload"))
        return _log_and_return("upload", provider_name, resolved_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("upload", provider_name, resolved_path, started_at, response, str(exc))


