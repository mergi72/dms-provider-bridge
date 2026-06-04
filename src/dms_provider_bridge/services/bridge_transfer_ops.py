from __future__ import annotations

import os
import math

from dms_provider_bridge.models.bridge import BridgeAuthContext
from dms_provider_bridge.models.operation import OperationResult


class TransferPrecheckError(ValueError):
    pass


class TransferNotFoundError(FileNotFoundError):
    pass


def estimated_binary_size_from_base64(content_base64: str) -> int:
    payload = content_base64.strip()
    if not payload:
        return 0
    pad = 0
    if payload.endswith("=="):
        pad = 2
    elif payload.endswith("="):
        pad = 1
    return max(0, math.floor(len(payload) * 3 / 4) - pad)


def max_cross_provider_upload_bytes(provider) -> int:
    config = getattr(provider, "config", {})
    if isinstance(config, dict):
        transfer_cfg = config.get("transfer", {})
        if isinstance(transfer_cfg, dict):
            value = transfer_cfg.get("maxBase64Bytes")
            if isinstance(value, int) and value > 0:
                return value
    return 20 * 1024 * 1024


def max_cross_provider_nodes(provider) -> int:
    config = getattr(provider, "config", {})
    if isinstance(config, dict):
        transfer_cfg = config.get("transfer", {})
        if isinstance(transfer_cfg, dict):
            value = transfer_cfg.get("maxNodes")
            if isinstance(value, int) and value > 0:
                return value
    return 500


def _split_parent_and_name(path: str) -> tuple[str, str]:
    normalized = (path or "").strip() or "/"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    normalized = normalized.rstrip("/") or "/"
    if normalized == "/":
        return "/", ""
    return normalized.rsplit("/", 1)[0] or "/", normalized.split("/")[-1]


def _join_child_path(parent: str, name: str) -> str:
    normalized_parent = parent.rstrip("/") or "/"
    return f"{normalized_parent}/{name}" if normalized_parent != "/" else f"/{name}"


def ensure_folder_chain(provider, target_folder_path: str, auth: BridgeAuthContext) -> None:
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
            raise TransferPrecheckError(f"Cross-provider copy failed: destination segment is not a folder: {current}")


def _cross_copy_file_fso_to_edocat(src_provider, dst_provider, src_file_path: str, dst_file_path: str, auth: BridgeAuthContext, max_bytes: int) -> tuple[str | None, int]:
    download_result = src_provider.download_item(src_file_path, auth)
    content_base64 = download_result.content_base64 or ""
    if not content_base64:
        raise TransferPrecheckError("Cross-provider copy failed: source download returned no content.")

    payload_bytes = download_result.size if isinstance(download_result.size, int) else estimated_binary_size_from_base64(content_base64)
    if payload_bytes > max_bytes:
        raise TransferPrecheckError(f"Cross-provider copy blocked: payload size {payload_bytes} B exceeds limit {max_bytes} B.")

    destination_parent, destination_name = _split_parent_and_name(dst_file_path)
    if not destination_name:
        raise TransferPrecheckError("Destination path must include a target file name.")

    ensure_folder_chain(dst_provider, destination_parent, auth)

    dst_provider.upload_item(
        destination_parent,
        destination_name,
        content_base64=content_base64,
        overwrite=False,
        auth=auth,
    )
    return download_result.mime_type, payload_bytes


def _file_payload_bytes(src_provider, item, auth: BridgeAuthContext) -> int:
    if isinstance(getattr(item, "size", None), int) and item.size >= 0:
        return item.size

    stat_item = src_provider.stat_item(item.path, auth)
    if stat_item is not None and isinstance(getattr(stat_item, "size", None), int) and stat_item.size >= 0:
        return stat_item.size

    download_result = src_provider.download_item(item.path, auth)
    content_base64 = download_result.content_base64 if isinstance(download_result.content_base64, str) else ""
    if not content_base64:
        raise TransferPrecheckError(f"Cross-provider copy failed: source download returned no content for {item.path}.")
    return download_result.size if isinstance(download_result.size, int) else estimated_binary_size_from_base64(content_base64)


def _preflight_fso_tree_limits(src_provider, source_folder_path: str, auth: BridgeAuthContext, max_nodes: int, max_bytes: int) -> tuple[int, int]:
    total_nodes = 0
    total_bytes = 0

    def walk(path: str) -> None:
        nonlocal total_nodes, total_bytes
        total_nodes += 1
        if total_nodes > max_nodes:
            raise TransferPrecheckError(f"Cross-provider copy blocked: source tree has {total_nodes} nodes, limit is {max_nodes}.")

        listing = src_provider.list_items(path, auth)
        for child in listing.items:
            if child.is_folder:
                walk(child.path)
                continue

            total_nodes += 1
            if total_nodes > max_nodes:
                raise TransferPrecheckError(f"Cross-provider copy blocked: source tree has {total_nodes} nodes, limit is {max_nodes}.")

            file_bytes = _file_payload_bytes(src_provider, child, auth)
            if file_bytes > max_bytes:
                raise TransferPrecheckError(f"Cross-provider copy blocked: payload size {file_bytes} B exceeds limit {max_bytes} B.")
            total_bytes += file_bytes

    walk(source_folder_path)
    return total_nodes, total_bytes


def _cross_copy_folder_fso_to_edocat(src_provider, dst_provider, source_folder_path: str, destination_folder_path: str, auth: BridgeAuthContext, max_bytes: int) -> tuple[int, int]:
    uploaded_files = 0
    uploaded_bytes = 0
    ensure_folder_chain(dst_provider, destination_folder_path, auth)
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


def copy_fso_to_edocat(src_provider, dst_provider, source_path: str, destination_path: str, auth: BridgeAuthContext) -> OperationResult:
    source_stat = src_provider.stat_item(source_path, auth)
    if source_stat is None:
        raise TransferNotFoundError(source_path)

    max_bytes = max_cross_provider_upload_bytes(dst_provider)
    if source_stat.is_folder:
        max_nodes = max_cross_provider_nodes(dst_provider)
        _preflight_fso_tree_limits(src_provider, source_path, auth, max_nodes, max_bytes)
        uploaded_files, uploaded_bytes = _cross_copy_folder_fso_to_edocat(
            src_provider,
            dst_provider,
            source_path,
            destination_path,
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
        mime_type, payload_bytes = _cross_copy_file_fso_to_edocat(
            src_provider,
            dst_provider,
            source_path,
            destination_path,
            auth,
            max_bytes,
        )
        result_message = f"mode=cross-provider;source={src_provider.name};destination={dst_provider.name};uploaded_files=1"

    return OperationResult(
        success=True,
        operation="copy",
        provider=dst_provider.name,
        source=source_path,
        destination=destination_path,
        message=result_message,
        mime_type=mime_type,
        size=payload_bytes,
    )


def upload_with_preflight(provider, destination_path: str, file_name: str, auth: BridgeAuthContext, content_base64: str | None = None, source_path: str | None = None, overwrite: bool = False) -> OperationResult:
    if source_path:
        try:
            os.path.getsize(source_path)
        except OSError as exc:
            raise TransferPrecheckError(f"Upload blocked: source file is not accessible: {source_path}") from exc
    else:
        max_bytes = max_cross_provider_upload_bytes(provider)
        payload_bytes = estimated_binary_size_from_base64(content_base64 or "")
        if payload_bytes > max_bytes:
            raise TransferPrecheckError(f"Upload blocked: payload size {payload_bytes} B exceeds limit {max_bytes} B.")
    ensure_folder_chain(provider, destination_path, auth)
    return provider.upload_item(destination_path, file_name, content_base64=content_base64, source_path=source_path, overwrite=overwrite, auth=auth)

