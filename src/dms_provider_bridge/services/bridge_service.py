from __future__ import annotations

import base64
import os
import tempfile
import time

from dms_provider_bridge.adapters.commander_api import WfxErrorCode, build_wfx_path, parse_wfx_path
from dms_provider_bridge.core.config_loader import load_connection_metadata
from dms_provider_bridge.core.logging import get_logger
from dms_provider_bridge.core.errors import ConnectionNotFoundError
from dms_provider_bridge.models.bridge import BridgeAuthContext, WfxResponse
from dms_provider_bridge.models.item import DmsItem
from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.services.auth_service import validate_bridge_auth
from dms_provider_bridge.services.auth_resolver import auth_requirements, resolve_effective_auth
from dms_provider_bridge.services.bridge_errors import map_exception
from dms_provider_bridge.services.connection_runtime_service import (
    get_connection_runtime,
    get_default_connection_name,
    list_registered_connections,
    runtime_registry_snapshot,
)
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
    provider = get_connection_runtime(parsed.connection)
    return provider, parsed


def _metadata(provider, operation: str) -> dict[str, str | None]:
    return {
        "connection": provider.name,
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


def _is_connection_root_path(path: str | None) -> bool:
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


def _item_version_metadata(prefix: str, connection_name: str, path: str, item: DmsItem | None) -> dict[str, object]:
    return {
        f"{prefix}_connection": connection_name,
        f"{prefix}_provider": connection_name,
        f"{prefix}_path": path,
        f"{prefix}_id": item.id if item is not None else None,
        f"{prefix}_name": item.name if item is not None else None,
        f"{prefix}_version": item.version_label if item is not None else None,
        f"{prefix}_version_type": item.version_type if item is not None else None,
        f"{prefix}_size": item.size if item is not None else None,
        f"{prefix}_modified_at": item.modified_at if item is not None else None,
    }


def _cross_provider_target_conflict_response(
    operation: str,
    src_provider,
    src_path: str,
    src_item: DmsItem | None,
    dst_provider,
    dst_path: str,
    dst_item: DmsItem,
) -> WfxResponse:
    metadata: dict[str, object] = {
        "action": "version_required",
        "reason": "target_exists",
        "operation": operation,
        "transfer": "download-upload" if operation == "copy" else "download-upload-delete",
        "allowed_actions": ["upload_as_new_version", "cancel"],
        "versioning": {
            "mode": "version",
            "majorVersion": False,
            "comment_supported": True,
        },
    }
    metadata.update(_item_version_metadata("source", src_provider.name, src_path, src_item))
    metadata.update(_item_version_metadata("target", dst_provider.name, dst_path, dst_item))
    metadata.update(
        {
            "connection": dst_provider.name,
            "provider": dst_provider.name,
            "destination_connection": dst_provider.name,
            "destination_provider": dst_provider.name,
            "path": dst_path,
            "name": dst_item.name,
            "node_id": dst_item.id,
            "current_version": dst_item.version_label,
            "current_version_type": dst_item.version_type,
            "current_modified_at": dst_item.modified_at,
        }
    )
    return _failure(
        WfxErrorCode.ACCESS_DENIED,
        f"Cross-provider {operation} target exists and requires version choice: {dst_path}",
        metadata,
    )


def _target_supports_versioning(provider) -> bool:
    capabilities = provider.versioning_capabilities() if callable(getattr(provider, "versioning_capabilities", None)) else {}
    return bool(capabilities.get("supported")) if isinstance(capabilities, dict) else False


def _cross_provider_overwrite_conflict_response(
    operation: str,
    src_provider,
    src_path: str,
    src_item: DmsItem | None,
    dst_provider,
    dst_path: str,
    dst_item: DmsItem,
) -> WfxResponse:
    metadata: dict[str, object] = {
        "action": "overwrite_required",
        "reason": "target_exists",
        "operation": operation,
        "transfer": "download-upload" if operation == "copy" else "download-upload-delete",
        "allowed_actions": ["overwrite", "cancel"],
        "versioning": {
            "supported": False,
        },
    }
    metadata.update(_item_version_metadata("source", src_provider.name, src_path, src_item))
    metadata.update(_item_version_metadata("target", dst_provider.name, dst_path, dst_item))
    metadata.update(
        {
            "connection": dst_provider.name,
            "provider": dst_provider.name,
            "destination_connection": dst_provider.name,
            "destination_provider": dst_provider.name,
            "path": dst_path,
            "name": dst_item.name,
            "node_id": dst_item.id,
        }
    )
    return _failure(
        WfxErrorCode.ACCESS_DENIED,
        f"Cross-provider {operation} target exists and requires overwrite choice: {dst_path}",
        metadata,
    )


def _cross_provider_existing_target_response(
    operation: str,
    src_provider,
    src_path: str,
    src_auth: BridgeAuthContext,
    dst_provider,
    dst_path: str,
    dst_auth: BridgeAuthContext,
    versioning: object,
    overwrite: bool = False,
) -> WfxResponse | None:
    target_item = dst_provider.stat_item(dst_path, dst_auth)
    if target_item is None:
        return None

    target_supports_versioning = _target_supports_versioning(dst_provider)
    if target_supports_versioning and _versioning_payload(versioning) is not None:
        return None
    if not target_supports_versioning and overwrite:
        return None

    source_item = src_provider.stat_item(src_path, src_auth)
    if target_supports_versioning:
        return _cross_provider_target_conflict_response(
            operation,
            src_provider,
            src_path,
            source_item,
            dst_provider,
            dst_path,
            target_item,
        )
    return _cross_provider_overwrite_conflict_response(
        operation,
        src_provider,
        src_path,
        source_item,
        dst_provider,
        dst_path,
        target_item,
    )


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


def _upload_downloaded_content(
    dst_provider,
    target_folder: str,
    file_name: str,
    auth: BridgeAuthContext,
    content_base64: str,
    versioning: dict | None = None,
    overwrite: bool = False,
):
    payload_size = estimated_binary_size_from_base64(content_base64)
    if payload_size <= max_inline_upload_bytes(dst_provider):
        return upload_with_preflight(
            dst_provider,
            target_folder,
            file_name,
            auth,
            content_base64=content_base64,
            overwrite=overwrite,
            versioning=versioning,
        )

    temp_path = _write_base64_to_temp_file(content_base64)
    try:
        return upload_with_preflight(
            dst_provider,
            target_folder,
            file_name,
            auth,
            source_path=temp_path,
            overwrite=overwrite,
            versioning=versioning,
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


def _validated_connection_auth(provider, auth: BridgeAuthContext) -> BridgeAuthContext:
    auth_copy = _copy_auth(auth)
    default_scheme = getattr(provider, "upstream_auth_scheme", None) or "basic"
    effective = resolve_effective_auth(
        getattr(provider, "config", None),
        auth_copy,
        default_scheme=default_scheme,
    )
    if effective.mode == "none":
        return auth_copy
    return BridgeAuthContext(
        mode="credentials",
        credential_id=effective.credential_id,
        target=effective.target,
        username=effective.username,
        password=effective.password,
        token=effective.token,
        win_user=effective.win_user,
    )


def _connection_root_listing() -> ListingResult:
    connections = list_registered_connections()
    items = [
        DmsItem(
            id=connection_name,
            name=connection_name,
            path=build_wfx_path(connection_name, "/"),
            is_folder=True,
            mime_type="application/x-dms-connection",
        )
        for connection_name in connections
    ]
    return ListingResult(provider="bridge", path="/", total=len(items), items=items)


def _default_connection_name_or_none() -> str | None:
    try:
        return get_default_connection_name()
    except Exception as exc:
        _LOGGER.warning("default_connection_unavailable error=%s", exc)
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
    upstream_auth_scheme = getattr(provider, "upstream_auth_scheme", "unknown")
    if upstream_auth_scheme == "none":
        return auth_requirements(config, default_scheme="none")
    return auth_requirements(config, default_scheme=upstream_auth_scheme)


def _log_and_return(
    operation: str,
    connection: str | None,
    path: str,
    started_at: float,
    response: WfxResponse,
    error: str | None = None,
) -> WfxResponse:
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    connection_value = connection or "-"
    error_value = error or response.message or ""
    level_method = _LOGGER.info if response.ok else _LOGGER.warning
    level_method(
        "bridge_operation operation=%s connection=%s provider=%s path=%s error=%s duration_ms=%d",
        operation,
        connection_value,
        connection_value,
        path,
        error_value,
        duration_ms,
    )
    return response


def connections_path() -> WfxResponse:
    started_at = time.perf_counter()
    registry = runtime_registry_snapshot()
    connections = list(registry["wfx_connections"])
    default_connection = _default_connection_name_or_none()
    response = _success(
        data={
            "connections": registry["connections"],
            "available_drivers": registry["available_drivers"],
            "connection_names": connections,
            "default_connection": default_connection,
        },
        metadata={"operation": "connections"},
    )
    return _log_and_return("connections", None, "/", started_at, response)


def connection_detail_path(connection_name: str) -> WfxResponse:
    started_at = time.perf_counter()
    try:
        provider = get_connection_runtime(connection_name)
        connection_metadata = load_connection_metadata(provider.name)
        response = _success(
            data={
                "name": provider.name,
                "kind": connection_metadata.get("kind") or "driver",
                "driver": connection_metadata.get("driver") or provider.name,
                "mount": connection_metadata.get("mount") or build_wfx_path(provider.name, "/"),
                "display_name": connection_metadata.get("display_name"),
                "description": connection_metadata.get("description"),
                "enabled": provider.name in list_registered_connections(),
                "auth": _provider_auth_requirements(provider),
                "capabilities": _provider_capabilities(provider),
                "versioning": _provider_versioning(provider),
            },
            metadata={"operation": "connection_detail", "connection": provider.name},
        )
        return _log_and_return("connection_detail", provider.name, "/", started_at, response)
    except ConnectionNotFoundError as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("connection_detail", connection_name, "/", started_at, response, str(exc))


def list_path(path: str, auth: BridgeAuthContext | None) -> WfxResponse:
    started_at = time.perf_counter()
    connection_name: str | None = None
    resolved_path = path
    try:
        if _is_connection_root_path(path):
            response = _success(
                data=_connection_root_listing().model_dump(),
                metadata={
                    "operation": "list",
                    "connection_root": True,
                    "connections": list_registered_connections(),
                    "default_connection": _default_connection_name_or_none(),
                },
            )
            return _log_and_return("list", "bridge", "/", started_at, response)
        provider, parsed = _resolve(path)
        connection_name = provider.name
        resolved_path = parsed.path
        auth_info = _provider_auth_requirements(provider)
        if auth is None and auth_info.get("required") is not False:
            response = _failure(WfxErrorCode.ACCESS_DENIED, "Authentication is required for provider paths.")
            return _log_and_return("list", connection_name, resolved_path, started_at, response, response.message)
        runtime_auth = _validated_connection_auth(provider, auth) if auth is not None else None
        listing = provider.list_items(parsed.path, runtime_auth)
        response = _success(data=listing.model_dump(), metadata=_metadata(provider, "list"))
        return _log_and_return("list", connection_name, resolved_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("list", connection_name, resolved_path, started_at, response, str(exc))


def stat_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    started_at = time.perf_counter()
    connection_name: str | None = None
    resolved_path = path
    try:
        provider, parsed = _resolve(path)
        connection_name = provider.name
        resolved_path = parsed.path
        runtime_auth = _validated_connection_auth(provider, auth)
        item = provider.stat_item(parsed.path, runtime_auth)
        if item is None:
            deduplicated_path = _deduplicate_repeated_leaf(parsed.path)
            if deduplicated_path and deduplicated_path != parsed.path:
                item = provider.stat_item(deduplicated_path, runtime_auth)
                if item is not None:
                    resolved_path = deduplicated_path
                    response = _success(data=item.model_dump(), metadata=_metadata(provider, "stat"))
                    return _log_and_return("stat", connection_name, resolved_path, started_at, response)

            response = _failure(WfxErrorCode.NOT_FOUND, f"Path not found: {path}")
            return _log_and_return("stat", connection_name, resolved_path, started_at, response, response.message)
        response = _success(data=item.model_dump(), metadata=_metadata(provider, "stat"))
        return _log_and_return("stat", connection_name, resolved_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("stat", connection_name, resolved_path, started_at, response, str(exc))


def mkdir_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    started_at = time.perf_counter()
    connection_name: str | None = None
    resolved_path = path
    try:
        provider, parsed = _resolve(path)
        connection_name = provider.name
        resolved_path = parsed.path
        runtime_auth = _validated_connection_auth(provider, auth)
        result = provider.make_dir(parsed.path, runtime_auth)
        response = _success(data=result.model_dump(), metadata=_metadata(provider, "mkdir"))
        return _log_and_return("mkdir", connection_name, resolved_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("mkdir", connection_name, resolved_path, started_at, response, str(exc))


def delete_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    started_at = time.perf_counter()
    connection_name: str | None = None
    resolved_path = path
    try:
        provider, parsed = _resolve(path)
        connection_name = provider.name
        resolved_path = parsed.path
        runtime_auth = _validated_connection_auth(provider, auth)
        result = provider.delete_item(parsed.path, runtime_auth)
        response = _success(data=result.model_dump(), metadata=_metadata(provider, "delete"))
        return _log_and_return("delete", connection_name, resolved_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("delete", connection_name, resolved_path, started_at, response, str(exc))


def rename_path(
    source: str,
    destination: str,
    auth: BridgeAuthContext,
    source_auth: BridgeAuthContext | None = None,
    destination_auth: BridgeAuthContext | None = None,
    versioning: object = None,
    overwrite: bool = False,
) -> WfxResponse:
    started_at = time.perf_counter()
    connection_name: str | None = None
    operation_path = f"{source} -> {destination}"
    try:
        src_provider, src = _resolve(source)
        dst_provider, dst = _resolve(destination)
        connection_name = src_provider.name
        operation_path = f"{src.path} -> {dst.path}"
        src_auth = _validated_connection_auth(src_provider, source_auth or auth)
        if src_provider.name != dst_provider.name:
            dst_auth = _validated_connection_auth(dst_provider, destination_auth or auth)
            target_folder, file_name = _split_parent_and_name(dst.path)
            if not file_name:
                response = _failure(WfxErrorCode.BAD_PATH, "Cross-provider move requires a destination file name.")
                return _log_and_return("rename", connection_name, operation_path, started_at, response, response.message)
            conflict_response = _cross_provider_existing_target_response(
                "move",
                src_provider,
                src.path,
                src_auth,
                dst_provider,
                dst.path,
                dst_auth,
                versioning,
                overwrite=overwrite,
            )
            if conflict_response is not None:
                return _log_and_return("rename", connection_name, operation_path, started_at, conflict_response, conflict_response.message)
            download_result = src_provider.download_item(src.path, src_auth)
            if not download_result.success:
                response = _failure(WfxErrorCode.INTERNAL_ERROR, _operation_failure_message("move download", download_result))
                return _log_and_return("rename", connection_name, operation_path, started_at, response, response.message)
            if not download_result.content_base64:
                response = _failure(WfxErrorCode.INTERNAL_ERROR, "Cross-provider move failed: source download returned no content.")
                return _log_and_return("rename", connection_name, operation_path, started_at, response, response.message)
            upload_result = _upload_downloaded_content(
                dst_provider,
                target_folder,
                file_name,
                dst_auth,
                download_result.content_base64,
                _versioning_payload(versioning),
                overwrite=overwrite,
            )
            if not upload_result.success:
                response = _failure(WfxErrorCode.INTERNAL_ERROR, _operation_failure_message("move upload", upload_result))
                return _log_and_return("rename", connection_name, operation_path, started_at, response, response.message)
            delete_result = src_provider.delete_item(src.path, src_auth)
            response = _success(
                data=upload_result.model_dump(),
                metadata={
                    "operation": "rename",
                    "transfer": "download-upload-delete",
                    "source_connection": src_provider.name,
                    "destination_connection": dst_provider.name,
                    "source_provider": src_provider.name,
                    "destination_provider": dst_provider.name,
                    "delete": delete_result.model_dump(),
                },
            )
            return _log_and_return("rename", connection_name, operation_path, started_at, response)
        result = src_provider.rename_item(src.path, dst.path, src_auth)
        response = _success(data=result.model_dump(), metadata=_metadata(src_provider, "rename"))
        return _log_and_return("rename", connection_name, operation_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("rename", connection_name, operation_path, started_at, response, str(exc))


def copy_path(
    source: str,
    destination: str,
    auth: BridgeAuthContext,
    source_auth: BridgeAuthContext | None = None,
    destination_auth: BridgeAuthContext | None = None,
    versioning: object = None,
    overwrite: bool = False,
) -> WfxResponse:
    started_at = time.perf_counter()
    connection_name: str | None = None
    operation_path = f"{source} -> {destination}"
    try:
        src_provider, src = _resolve(source)
        dst_provider, dst = _resolve(destination)
        connection_name = f"{src_provider.name}->{dst_provider.name}"
        operation_path = f"{src.path} -> {dst.path}"
        src_auth = _validated_connection_auth(src_provider, source_auth or auth)
        if src_provider.name == dst_provider.name:
            result = src_provider.copy_item(src.path, dst.path, src_auth)
            response = _success(data=result.model_dump(), metadata=_metadata(src_provider, "copy"))
            return _log_and_return("copy", connection_name, operation_path, started_at, response)

        dst_auth = _validated_connection_auth(dst_provider, destination_auth or auth)
        target_folder, file_name = _split_parent_and_name(dst.path)
        if not file_name:
            response = _failure(WfxErrorCode.BAD_PATH, "Cross-provider copy requires a destination file name.")
            return _log_and_return("copy", connection_name, operation_path, started_at, response, response.message)
        conflict_response = _cross_provider_existing_target_response(
            "copy",
            src_provider,
            src.path,
            src_auth,
            dst_provider,
            dst.path,
            dst_auth,
            versioning,
            overwrite=overwrite,
        )
        if conflict_response is not None:
            return _log_and_return("copy", connection_name, operation_path, started_at, conflict_response, conflict_response.message)
        download_result = src_provider.download_item(src.path, src_auth)
        if not download_result.success:
            response = _failure(WfxErrorCode.INTERNAL_ERROR, _operation_failure_message("copy download", download_result))
            return _log_and_return("copy", connection_name, operation_path, started_at, response, response.message)
        if not download_result.content_base64:
            response = _failure(WfxErrorCode.INTERNAL_ERROR, "Cross-provider copy failed: source download returned no content.")
            return _log_and_return("copy", connection_name, operation_path, started_at, response, response.message)
        upload_result = _upload_downloaded_content(
            dst_provider,
            target_folder,
            file_name,
            dst_auth,
            download_result.content_base64,
            _versioning_payload(versioning),
            overwrite=overwrite,
        )
        if not upload_result.success:
            response = _failure(WfxErrorCode.INTERNAL_ERROR, _operation_failure_message("copy upload", upload_result))
            return _log_and_return("copy", connection_name, operation_path, started_at, response, response.message)
        response = _success(
            data=upload_result.model_dump(),
            metadata={
                "operation": "copy",
                "transfer": "download-upload",
                "source_connection": src_provider.name,
                "destination_connection": dst_provider.name,
                "source_provider": src_provider.name,
                "destination_provider": dst_provider.name,
            },
        )
        return _log_and_return("copy", connection_name, operation_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("copy", connection_name, operation_path, started_at, response, str(exc))


def download_path(path: str, auth: BridgeAuthContext) -> WfxResponse:
    started_at = time.perf_counter()
    connection_name: str | None = None
    resolved_path = path
    try:
        provider, parsed = _resolve(path)
        connection_name = provider.name
        resolved_path = parsed.path
        runtime_auth = _validated_connection_auth(provider, auth)
        result = provider.download_item(parsed.path, runtime_auth)
        response = _success(data=result.model_dump(), metadata=_metadata(provider, "download"))
        return _log_and_return("download", connection_name, resolved_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("download", connection_name, resolved_path, started_at, response, str(exc))


def open_download_stream(path: str, auth: BridgeAuthContext) -> WfxResponse | None:
    started_at = time.perf_counter()
    connection_name: str | None = None
    resolved_path = path
    try:
        provider, parsed = _resolve(path)
        connection_name = provider.name
        resolved_path = parsed.path
        stream_item = getattr(provider, "stream_item", None)
        if not callable(stream_item):
            return None
        runtime_auth = _validated_connection_auth(provider, auth)
        result = stream_item(parsed.path, runtime_auth)
        response = _success(data=result, metadata=_metadata(provider, "download"))
        return _log_and_return("download_raw_stream", connection_name, resolved_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("download_raw_stream", connection_name, resolved_path, started_at, response, str(exc))


def upload_path(destination: str, file_name: str, auth: BridgeAuthContext, content_base64: str | None = None, source_path: str | None = None, overwrite: bool = False, versioning: dict | None = None) -> WfxResponse:
    started_at = time.perf_counter()
    connection_name: str | None = None
    resolved_path = destination
    try:
        provider, parsed = _resolve(destination)
        connection_name = provider.name
        resolved_path = parsed.path
        runtime_auth = _validated_connection_auth(provider, auth)
        try:
            result = upload_with_preflight(provider, parsed.path, file_name, runtime_auth, content_base64=content_base64, source_path=source_path, overwrite=overwrite, versioning=_versioning_payload(versioning))
        except Exception as exc:
            response = _failure_from_exception(exc)
            return _log_and_return("upload", connection_name, resolved_path, started_at, response, str(exc))
        response = _success(data=result.model_dump(), metadata=_metadata(provider, "upload"))
        return _log_and_return("upload", connection_name, resolved_path, started_at, response)
    except Exception as exc:
        response = _failure_from_exception(exc)
        return _log_and_return("upload", connection_name, resolved_path, started_at, response, str(exc))


