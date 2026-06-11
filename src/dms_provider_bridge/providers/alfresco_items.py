from __future__ import annotations

from collections.abc import Callable

from dms_provider_bridge.models.item import DmsItem


def item_from_entry(
    entry: dict,
    fallback_path: str | None,
    normalize_path: Callable[[str], str],
    node_id_from_path: Callable[[str], str],
) -> DmsItem:
    props = entry.get("properties", {}) if isinstance(entry.get("properties"), dict) else {}
    name = entry.get("name") or (fallback_path.rstrip("/").split("/")[-1] if fallback_path else "") or "/"
    path = fallback_path or entry.get("path", {}).get("name", "/") or "/"
    is_folder = entry.get("isFolder") if isinstance(entry.get("isFolder"), bool) else str(entry.get("nodeType", "")).endswith("folder")
    modified_at = entry.get("modifiedAt")
    if modified_at is not None:
        modified_at = str(modified_at)
    lock_type = props.get("cm:lockType")
    is_read_only = bool(lock_type) if lock_type is not None else None
    content = entry.get("content")
    return DmsItem(
        id=str(entry.get("id") or node_id_from_path(path)),
        name=str(name),
        path=normalize_path(path),
        is_folder=bool(is_folder),
        size=content.get("sizeInBytes") if isinstance(content, dict) else None,
        mime_type=content.get("mimeType") if isinstance(content, dict) else props.get("cm:content.mimetype"),
        modified_at=modified_at,
        is_read_only=is_read_only,
    )
