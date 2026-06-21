from __future__ import annotations

from urllib.parse import unquote

from dms_provider_bridge.adapters.commander_api import WfxErrorCode, build_wfx_path
from dms_provider_bridge.core.connection_aliases import resolve_connection_path_override
from dms_provider_bridge.models.bridge import BridgeAuthContext, WfxResponse
from dms_provider_bridge.services.bridge_errors import map_exception
from dms_provider_bridge.services.connection_runtime_service import get_connection_runtime


def _success(data: object = None, message: str | None = None, metadata: dict | None = None) -> WfxResponse:
    return WfxResponse(ok=True, error_code=WfxErrorCode.OK, message=message, data=data, metadata=metadata)


def _failure(code: int, message: str, metadata: dict | None = None) -> WfxResponse:
    return WfxResponse(ok=False, error_code=code, message=message, data=None, metadata=metadata)


def _failure_from_exception(exc: Exception) -> WfxResponse:
    mapped = map_exception(exc)
    return _failure(mapped.code, mapped.message, mapped.metadata)


def _normalize_connection_path(path: str, empty_message: str) -> str | WfxResponse:
    normalized = unquote(path).replace("\\", "/").strip()
    if not normalized:
        return _failure(WfxErrorCode.BAD_PATH, empty_message)
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized


def _resolve_source_path_override(
    connection_path_override: str | None,
    legacy_provider_path_override: str | None,
) -> str | WfxResponse | None:
    try:
        return resolve_connection_path_override(connection_path_override, legacy_provider_path_override)
    except ValueError as exc:
        return _failure(WfxErrorCode.BAD_PATH, str(exc))


def resolve_share_url(share_url: str, connection_name: str) -> WfxResponse:
    try:
        connection_runtime = get_connection_runtime(connection_name)
        if not connection_runtime.supports_share_url():
            return _failure(WfxErrorCode.NOT_SUPPORTED, f"Connection does not support share URL resolution: {connection_name}")

        normalized = connection_runtime.share_url_to_path(share_url)
        wfx_path = build_wfx_path(connection_runtime.name, normalized)
        return _success(
            data={
                "connection": connection_runtime.name,
                "provider": connection_runtime.name,
                "path": wfx_path,
                "share_path": normalized,
                "source_url": share_url,
            },
            metadata={"connection": connection_runtime.name, "provider": connection_runtime.name, "operation": "resolve-share-url"},
        )
    except Exception as exc:
        return _failure_from_exception(exc)


def browse_share_url(
    share_url: str,
    auth: BridgeAuthContext | None,
    connection_name: str,
    operation: str = "list",
    execute: bool = True,
    connection_path_override: str | None = None,
    destination_share_url: str | None = None,
    destination_path_override: str | None = None,
    file_name: str | None = None,
    content_base64: str | None = None,
    overwrite: bool = False,
    versioning: dict | None = None,
    provider_path_override: str | None = None,
) -> WfxResponse:
    from dms_provider_bridge.services import bridge_service

    source_path_override = _resolve_source_path_override(connection_path_override, provider_path_override)
    if isinstance(source_path_override, WfxResponse):
        return source_path_override

    if not execute:
        validated = validate_browse_share_url(
            share_url,
            connection_name,
            operation,
            source_path_override,
            destination_share_url,
            destination_path_override,
            file_name,
        )
        if not validated.ok:
            return validated
        metadata = dict(validated.metadata or {})
        metadata["operation"] = f"browse-share-url:dry-run:{operation}"
        payload = dict(validated.data) if isinstance(validated.data, dict) else {"validated": validated.data}
        payload["executed"] = False
        return _success(data=payload, metadata=metadata)

    resolved = resolve_share_url(share_url, connection_name)
    if not resolved.ok:
        return resolved

    if not isinstance(resolved.data, dict):
        return _failure(WfxErrorCode.INTERNAL_ERROR, "Resolved share URL payload has invalid format.")

    resolved_payload = dict(resolved.data)
    path = str(resolved_payload.get("path", ""))
    path_source = "share_url"
    if source_path_override:
        normalized_override = _normalize_connection_path(source_path_override, "connection_path_override is empty.")
        if isinstance(normalized_override, WfxResponse):
            return normalized_override
        path = build_wfx_path(connection_name, normalized_override)
        resolved_payload["path"] = path
        resolved_payload["share_path"] = normalized_override
        path_source = "connection_path_override"

    if not path:
        return _failure(WfxErrorCode.BAD_PATH, "Resolved share URL does not contain a target path.")

    if execute and auth is None:
        return _failure(WfxErrorCode.ACCESS_DENIED, "Auth is required when execute=true.")

    response: WfxResponse
    destination_path: str | None = None
    destination_source: str | None = None

    if operation == "list":
        response = bridge_service.list_path(path, auth)
    elif operation == "stat":
        response = bridge_service.stat_path(path, auth)
    elif operation == "download":
        response = bridge_service.download_path(path, auth)
    elif operation == "mkdir":
        response = bridge_service.mkdir_path(path, auth)
    elif operation == "delete":
        response = bridge_service.delete_path(path, auth)
    elif operation in {"copy", "move"}:
        if destination_path_override:
            normalized_destination = _normalize_connection_path(destination_path_override, "destination_path_override is empty.")
            if isinstance(normalized_destination, WfxResponse):
                return normalized_destination
            destination_path = build_wfx_path(connection_name, normalized_destination)
            destination_source = "destination_path_override"
        elif destination_share_url:
            destination_resolved = resolve_share_url(destination_share_url, connection_name)
            if not destination_resolved.ok:
                return destination_resolved
            if not isinstance(destination_resolved.data, dict):
                return _failure(WfxErrorCode.INTERNAL_ERROR, "Resolved destination share URL payload has invalid format.")
            destination_path = str(destination_resolved.data.get("path", ""))
            destination_source = "destination_share_url"
        else:
            return _failure(WfxErrorCode.BAD_PATH, "copy/move requires destination_path_override or destination_share_url.")

        if not destination_path:
            return _failure(WfxErrorCode.BAD_PATH, "Destination path is empty.")

        response = bridge_service.copy_path(path, destination_path, auth) if operation == "copy" else bridge_service.rename_path(path, destination_path, auth)
    elif operation == "upload":
        if not file_name:
            return _failure(WfxErrorCode.BAD_PATH, "upload requires file_name.")

        upload_destination_path = path
        upload_destination_source = path_source
        if destination_path_override:
            normalized_destination = _normalize_connection_path(destination_path_override, "destination_path_override is empty.")
            if isinstance(normalized_destination, WfxResponse):
                return normalized_destination
            upload_destination_path = build_wfx_path(connection_name, normalized_destination)
            upload_destination_source = "destination_path_override"
        elif destination_share_url:
            destination_resolved = resolve_share_url(destination_share_url, connection_name)
            if not destination_resolved.ok:
                return destination_resolved
            if not isinstance(destination_resolved.data, dict):
                return _failure(WfxErrorCode.INTERNAL_ERROR, "Resolved destination share URL payload has invalid format.")
            upload_destination_path = str(destination_resolved.data.get("path", ""))
            upload_destination_source = "destination_share_url"

        if not upload_destination_path:
            return _failure(WfxErrorCode.BAD_PATH, "Upload destination path is empty.")

        response = bridge_service.upload_path(
            upload_destination_path,
            file_name,
            auth,
            content_base64=content_base64,
            overwrite=overwrite,
            versioning=versioning,
        )
        destination_path = upload_destination_path
        destination_source = upload_destination_source
    else:
        return _failure(WfxErrorCode.NOT_SUPPORTED, f"Unsupported operation for share URL browsing: {operation}")

    if not response.ok:
        return response

    merged_data = {
        "resolved": resolved_payload,
        "path_source": path_source,
        "result": response.data,
    }
    if operation in {"copy", "move", "upload"} and destination_path and destination_source:
        merged_data["destination"] = {
            "path": destination_path,
            "path_source": destination_source,
        }
    merged_meta = dict(response.metadata or {})
    merged_meta["operation"] = f"browse-share-url:{operation}"
    return _success(data=merged_data, metadata=merged_meta)


def validate_browse_share_url(
    share_url: str,
    connection_name: str,
    operation: str = "list",
    connection_path_override: str | None = None,
    destination_share_url: str | None = None,
    destination_path_override: str | None = None,
    file_name: str | None = None,
    provider_path_override: str | None = None,
) -> WfxResponse:
    source_path_override = _resolve_source_path_override(connection_path_override, provider_path_override)
    if isinstance(source_path_override, WfxResponse):
        return source_path_override

    resolved = resolve_share_url(share_url, connection_name)
    if not resolved.ok:
        return resolved

    if not isinstance(resolved.data, dict):
        return _failure(WfxErrorCode.INTERNAL_ERROR, "Resolved share URL payload has invalid format.")

    resolved_payload = dict(resolved.data)
    source_path = str(resolved_payload.get("path", ""))
    source_path_source = "share_url"
    if source_path_override:
        normalized_override = _normalize_connection_path(source_path_override, "connection_path_override is empty.")
        if isinstance(normalized_override, WfxResponse):
            return normalized_override
        source_path = build_wfx_path(connection_name, normalized_override)
        source_path_source = "connection_path_override"
        resolved_payload["path"] = source_path
        resolved_payload["share_path"] = normalized_override

    if not source_path:
        return _failure(WfxErrorCode.BAD_PATH, "Resolved share URL does not contain a source path.")

    supported = {"list", "stat", "download", "copy", "move", "mkdir", "delete", "upload"}
    if operation not in supported:
        return _failure(WfxErrorCode.NOT_SUPPORTED, f"Unsupported operation for share URL validation: {operation}")

    destination_path = None
    destination_path_source = None
    if operation in {"copy", "move", "upload"}:
        if destination_path_override:
            normalized_destination = _normalize_connection_path(destination_path_override, "destination_path_override is empty.")
            if isinstance(normalized_destination, WfxResponse):
                return normalized_destination
            destination_path = build_wfx_path(connection_name, normalized_destination)
            destination_path_source = "destination_path_override"
        elif destination_share_url:
            destination_resolved = resolve_share_url(destination_share_url, connection_name)
            if not destination_resolved.ok:
                return destination_resolved
            if not isinstance(destination_resolved.data, dict):
                return _failure(WfxErrorCode.INTERNAL_ERROR, "Resolved destination share URL payload has invalid format.")
            destination_path = str(destination_resolved.data.get("path", ""))
            destination_path_source = "destination_share_url"
        elif operation == "upload":
            destination_path = source_path
            destination_path_source = source_path_source
        else:
            return _failure(WfxErrorCode.BAD_PATH, "copy/move requires destination_path_override or destination_share_url.")

        if not destination_path:
            return _failure(WfxErrorCode.BAD_PATH, "Destination path is empty.")

    if operation == "upload" and not file_name:
        return _failure(WfxErrorCode.BAD_PATH, "upload requires file_name.")

    payload = {
        "resolved": resolved_payload,
        "source": {
            "path": source_path,
            "path_source": source_path_source,
        },
        "can_execute": True,
        "operation": operation,
    }
    if destination_path and destination_path_source:
        payload["destination"] = {
            "path": destination_path,
            "path_source": destination_path_source,
        }
    if operation == "upload":
        payload["upload"] = {
            "file_name": file_name,
            "requires_content_base64": False,
        }

    return _success(
        data=payload,
        metadata={
            "connection": connection_name,
            "provider": connection_name,
            "operation": f"browse-share-url-validate:{operation}",
        },
    )
