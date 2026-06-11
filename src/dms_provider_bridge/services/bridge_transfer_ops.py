from __future__ import annotations

import os
import math

from dms_provider_bridge.models.bridge import BridgeAuthContext
from dms_provider_bridge.models.operation import OperationResult


class TransferPrecheckError(ValueError):
    pass


INLINE_UPLOAD_MAX_BYTES_DEFAULT = 4 * 1024 * 1024


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


def max_inline_upload_bytes(provider) -> int:
    transfer_limit = max_cross_provider_upload_bytes(provider)
    config = getattr(provider, "config", {})
    if isinstance(config, dict):
        upload_cfg = config.get("upload", {})
        if isinstance(upload_cfg, dict):
            inline_cfg = upload_cfg.get("inline", {})
            if isinstance(inline_cfg, dict):
                value = inline_cfg.get("maxBytes")
                if isinstance(value, int) and value > 0:
                    return min(value, transfer_limit)
    return min(INLINE_UPLOAD_MAX_BYTES_DEFAULT, transfer_limit)


def _split_parent_and_name(path: str) -> tuple[str, str]:
    normalized = (path or "").strip() or "/"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    normalized = normalized.rstrip("/") or "/"
    if normalized == "/":
        return "/", ""
    return normalized.rsplit("/", 1)[0] or "/", normalized.split("/")[-1]


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
            raise TransferPrecheckError(f"Upload failed: destination segment is not a folder: {current}")


def upload_with_preflight(provider, destination_path: str, file_name: str, auth: BridgeAuthContext, content_base64: str | None = None, source_path: str | None = None, overwrite: bool = False, versioning: dict | None = None) -> OperationResult:
    if source_path:
        try:
            os.path.getsize(source_path)
        except OSError as exc:
            raise TransferPrecheckError(f"Upload blocked: source file is not accessible: {source_path}") from exc
    else:
        max_bytes = max_inline_upload_bytes(provider)
        payload_bytes = estimated_binary_size_from_base64(content_base64 or "")
        if payload_bytes > max_bytes:
            raise TransferPrecheckError(
                f"Upload blocked: inline content_base64 payload size {payload_bytes} B exceeds limit {max_bytes} B. "
                "Use /bridge/wfx/upload-raw (or /bridge/wfx/upload-stream) with multipart/form-data for larger files."
            )
    ensure_folder_chain(provider, destination_path, auth)
    kwargs = {
        "content_base64": content_base64,
        "source_path": source_path,
        "overwrite": overwrite,
        "auth": auth,
    }
    if versioning is not None:
        kwargs["versioning"] = versioning
    return provider.upload_item(destination_path, file_name, **kwargs)

