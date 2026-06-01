from __future__ import annotations

import math
from urllib.parse import unquote, urlparse

from edocat_bridge.adapters.commander_api import WfxErrorCode, build_wfx_path, parse_wfx_path
from edocat_bridge.core.errors import AuthenticationError, ProviderNotFoundError
from edocat_bridge.models.bridge import BridgeAuthContext, WfxResponse
from edocat_bridge.models.operation import OperationResult
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


def _split_parent_and_name(path: str) -> tuple[str, str]:
    normalized = (path or "").strip() or "/"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    normalized = normalized.rstrip("/") or "/"
    if normalized == "/":
        return "/", ""
    return normalized.rsplit("/", 1)[0] or "/", normalized.split("/")[-1]


def _estimated_binary_size_from_base64(content_base64: str) -> int:
    payload = content_base64.strip()
    if not payload:
        return 0
    pad = 0
    if payload.endswith("=="):
        pad = 2
    elif payload.endswith("="):
        pad = 1
    return max(0, math.floor(len(payload) * 3 / 4) - pad)


def _max_cross_provider_upload_bytes(provider) -> int:
    config = getattr(provider, "config", {})
    if isinstance(config, dict):
        transfer_cfg = config.get("transfer", {})
        if isinstance(transfer_cfg, dict):
            value = transfer_cfg.get("maxBase64Bytes")
            if isinstance(value, int) and value > 0:
                return value
    return 20 * 1024 * 1024


def _max_cross_provider_nodes(provider) -> int:
    config = getattr(provider, "config", {})
    if isinstance(config, dict):
        transfer_cfg = config.get("transfer", {})
        if isinstance(transfer_cfg, dict):
            value = transfer_cfg.get("maxNodes")
            if isinstance(value, int) and value > 0:
                return value
    return 500


def _join_child_path(parent: str, name: str) -> str:
    normalized_parent = parent.rstrip("/") or "/"
    return f"{normalized_parent}/{name}" if normalized_parent != "/" else f"/{name}"


def _ensure_folder_chain(provider, target_folder_path: str, auth: BridgeAuthContext) -> None:
    normalized = (target_folder_path or "").strip() or "/"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    normalized = normalized.rstrip("/") or "/"
    if normalized == "/":
        return

    current = ""
    for part in normalized.strip("/").split("/"):
        current = f"{current}/{part}" if current else f"/{part}"
        existing = provider.stat_item(current, auth)
        if existing is None:
            provider.make_dir(current, auth)
            continue
        if not existing.is_folder:
            raise ValueError(f"Cross-provider copy failed: destination segment is not a folder: {current}")


def _cross_copy_file_fso_to_edocat(src_provider, dst_provider, src_file_path: str, dst_file_path: str, auth: BridgeAuthContext, max_bytes: int) -> tuple[str | None, int]:
    download_result = src_provider.download_item(src_file_path, auth)
    content_base64 = download_result.content_base64 or ""
    if not content_base64:
        raise ValueError("Cross-provider copy failed: source download returned no content.")

    payload_bytes = download_result.size if isinstance(download_result.size, int) else _estimated_binary_size_from_base64(content_base64)
    if payload_bytes > max_bytes:
        raise ValueError(f"Cross-provider copy blocked: payload size {payload_bytes} B exceeds limit {max_bytes} B.")

    destination_parent, destination_name = _split_parent_and_name(dst_file_path)
    if not destination_name:
        raise ValueError("Destination path must include a target file name.")

    _ensure_folder_chain(dst_provider, destination_parent, auth)

    dst_provider.upload_item(
        destination_parent,
        destination_name,
        content_base64=content_base64,
        overwrite=False,
        auth=auth,
    )
    return download_result.mime_type, payload_bytes


def _count_fso_tree_nodes(src_provider, source_folder_path: str, auth: BridgeAuthContext) -> int:
    listing = src_provider.list_items(source_folder_path, auth)
    total = 1
    for item in listing.items:
        if item.is_folder:
            total += _count_fso_tree_nodes(src_provider, item.path, auth)
        else:
            total += 1
    return total


def _file_payload_bytes(src_provider, item, auth: BridgeAuthContext) -> int:
    if isinstance(getattr(item, "size", None), int) and item.size >= 0:
        return item.size

    stat_item = src_provider.stat_item(item.path, auth)
    if stat_item is not None and isinstance(getattr(stat_item, "size", None), int) and stat_item.size >= 0:
        return stat_item.size

    download_result = src_provider.download_item(item.path, auth)
    content_base64 = download_result.content_base64 if isinstance(download_result.content_base64, str) else ""
    if not content_base64:
        raise ValueError(f"Cross-provider copy failed: source download returned no content for {item.path}.")
    return download_result.size if isinstance(download_result.size, int) else _estimated_binary_size_from_base64(content_base64)


def _preflight_fso_tree_limits(src_provider, source_folder_path: str, auth: BridgeAuthContext, max_nodes: int, max_bytes: int) -> tuple[int, int]:
    total_nodes = 0
    total_bytes = 0

    def walk(path: str) -> None:
        nonlocal total_nodes, total_bytes
        total_nodes += 1
        if total_nodes > max_nodes:
            raise ValueError(f"Cross-provider copy blocked: source tree has {total_nodes} nodes, limit is {max_nodes}.")

        listing = src_provider.list_items(path, auth)
        for child in listing.items:
            if child.is_folder:
                walk(child.path)
                continue

            total_nodes += 1
            if total_nodes > max_nodes:
                raise ValueError(f"Cross-provider copy blocked: source tree has {total_nodes} nodes, limit is {max_nodes}.")

            file_bytes = _file_payload_bytes(src_provider, child, auth)
            if file_bytes > max_bytes:
                raise ValueError(f"Cross-provider copy blocked: payload size {file_bytes} B exceeds limit {max_bytes} B.")
            total_bytes += file_bytes

    walk(source_folder_path)
    return total_nodes, total_bytes


def _cross_copy_folder_fso_to_edocat(src_provider, dst_provider, source_folder_path: str, destination_folder_path: str, auth: BridgeAuthContext, max_bytes: int) -> tuple[int, int]:
    uploaded_files = 0
    uploaded_bytes = 0
    _ensure_folder_chain(dst_provider, destination_folder_path, auth)
    listing = src_provider.list_items(source_folder_path, auth)
    for item in listing.items:
        dst_child_path = _join_child_path(destination_folder_path, item.name)
        if item.is_folder:
            child_files, child_bytes = _cross_copy_folder_fso_to_edocat(src_provider, dst_provider, item.path, dst_child_path, auth, max_bytes)
            uploaded_files += child_files
            uploaded_bytes += child_bytes
            continue

        _, file_bytes = _cross_copy_file_fso_to_edocat(src_provider, dst_provider, item.path, dst_child_path, auth, max_bytes)
        uploaded_files += 1
        uploaded_bytes += file_bytes
    return uploaded_files, uploaded_bytes


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
        if src_provider.name == dst_provider.name:
            result = src_provider.copy_item(src.path, dst.path, auth)
            return _success(data=result.model_dump(), metadata=_metadata(src_provider, "copy"))

        # First supported cross-provider flow: local file system -> eDoCat.
        if not (src_provider.name == "fso" and dst_provider.name == "edocat"):
            return _failure(WfxErrorCode.NOT_SUPPORTED, "Cross-provider copy is supported only for fso -> edocat.")

        source_stat = src_provider.stat_item(src.path, auth)
        if source_stat is None:
            return _failure(WfxErrorCode.NOT_FOUND, f"Path not found: {source}")

        max_bytes = _max_cross_provider_upload_bytes(dst_provider)
        if source_stat.is_folder:
            max_nodes = _max_cross_provider_nodes(dst_provider)
            try:
                total_nodes, _ = _preflight_fso_tree_limits(src_provider, src.path, auth, max_nodes, max_bytes)
            except ValueError as exc:
                return _failure(
                    WfxErrorCode.INTERNAL_ERROR,
                    str(exc),
                )
            uploaded_files, uploaded_bytes = _cross_copy_folder_fso_to_edocat(
                src_provider,
                dst_provider,
                src.path,
                dst.path,
                auth,
                max_bytes,
            )
            mime_type = None
            result_message = (
                f"mode=cross-provider;source={src_provider.name};destination={dst_provider.name};"
                f"uploaded_files={uploaded_files};uploaded_bytes={uploaded_bytes}"
            )
            payload_bytes = uploaded_bytes
        else:
            try:
                mime_type, payload_bytes = _cross_copy_file_fso_to_edocat(
                    src_provider,
                    dst_provider,
                    src.path,
                    dst.path,
                    auth,
                    max_bytes,
                )
            except ValueError as exc:
                return _failure(WfxErrorCode.INTERNAL_ERROR, str(exc))
            result_message = f"mode=cross-provider;source={src_provider.name};destination={dst_provider.name};uploaded_files=1"

        result = OperationResult(
            success=True,
            operation="copy",
            provider=dst_provider.name,
            source=src.path,
            destination=dst.path,
            message=result_message,
            mime_type=mime_type,
            size=payload_bytes,
        )
        return _success(data=result.model_dump(), metadata=_metadata(dst_provider, "upload"))
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
        max_bytes = _max_cross_provider_upload_bytes(provider)
        payload_bytes = _estimated_binary_size_from_base64(content_base64 or "")
        if payload_bytes > max_bytes:
            return _failure(WfxErrorCode.INTERNAL_ERROR, f"Upload blocked: payload size {payload_bytes} B exceeds limit {max_bytes} B.")
        _ensure_folder_chain(provider, parsed.path, auth)
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
    auth: BridgeAuthContext | None,
    provider: str = "alfresco",
    operation: str = "list",
    execute: bool = True,
    provider_path_override: str | None = None,
    destination_share_url: str | None = None,
    destination_path_override: str | None = None,
    file_name: str | None = None,
    content_base64: str | None = None,
    overwrite: bool = False,
) -> WfxResponse:
    if not execute:
        validated = validate_browse_share_url(
            share_url,
            provider,
            operation,
            provider_path_override,
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

    if execute and auth is None:
        return _failure(WfxErrorCode.ACCESS_DENIED, "Auth is required when execute=true.")

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


def validate_browse_share_url(
    share_url: str,
    provider: str = "alfresco",
    operation: str = "list",
    provider_path_override: str | None = None,
    destination_share_url: str | None = None,
    destination_path_override: str | None = None,
    file_name: str | None = None,
) -> WfxResponse:
    resolved = resolve_share_url(share_url, provider)
    if not resolved.ok:
        return resolved

    if not isinstance(resolved.data, dict):
        return _failure(WfxErrorCode.INTERNAL_ERROR, "Resolved share URL payload has invalid format.")

    resolved_payload = dict(resolved.data)
    source_path = str(resolved_payload.get("path", ""))
    source_path_source = "share_url"
    if provider_path_override:
        normalized_override = unquote(provider_path_override).replace("\\", "/").strip()
        if not normalized_override:
            return _failure(WfxErrorCode.BAD_PATH, "provider_path_override is empty.")
        if not normalized_override.startswith("/"):
            normalized_override = f"/{normalized_override}"
        source_path = build_wfx_path(provider, normalized_override)
        source_path_source = "provider_path_override"
        resolved_payload["path"] = source_path
        resolved_payload["share_path"] = normalized_override

    if not source_path:
        return _failure(WfxErrorCode.BAD_PATH, "Resolved share URL does not contain a source path.")

    supported = {"list", "stat", "download", "copy", "rename", "mkdir", "delete", "upload"}
    if operation not in supported:
        return _failure(WfxErrorCode.NOT_SUPPORTED, f"Unsupported operation for share URL validation: {operation}")

    destination_path = None
    destination_path_source = None
    if operation in {"copy", "rename", "upload"}:
        if destination_path_override:
            normalized_destination = unquote(destination_path_override).replace("\\", "/").strip()
            if not normalized_destination:
                return _failure(WfxErrorCode.BAD_PATH, "destination_path_override is empty.")
            if not normalized_destination.startswith("/"):
                normalized_destination = f"/{normalized_destination}"
            destination_path = build_wfx_path(provider, normalized_destination)
            destination_path_source = "destination_path_override"
        elif destination_share_url:
            destination_resolved = resolve_share_url(destination_share_url, provider)
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
            return _failure(
                WfxErrorCode.BAD_PATH,
                "copy/rename requires destination_path_override or destination_share_url.",
            )

        if not destination_path:
            return _failure(WfxErrorCode.BAD_PATH, "Destination path is empty.")

    if operation == "upload" and not file_name:
        return _failure(WfxErrorCode.BAD_PATH, "upload requires file_name.")

    payload: dict[str, object] = {
        "resolved": resolved_payload,
        "operation": operation,
        "source": {
            "path": source_path,
            "path_source": source_path_source,
        },
        "can_execute": True,
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
            "provider": provider,
            "operation": f"browse-share-url-validate:{operation}",
        },
    )
