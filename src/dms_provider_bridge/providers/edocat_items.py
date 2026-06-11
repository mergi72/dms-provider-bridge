from __future__ import annotations

from collections.abc import Callable

from dms_provider_bridge.models.item import DmsItem
from dms_provider_bridge.providers import edocat_nodes


def item_from_node(node: dict, fallback_path: str, public_path: Callable[[str], str]) -> DmsItem:
    node_path = str(node.get("_normalized_path") or "") or fallback_path
    exposed_path = public_path(node_path)
    name = str(node.get("name") or node_path.rstrip("/").split("/")[-1] or "/")
    size = node.get("size")
    if not isinstance(size, int):
        size = None
    modified_at = (
        node.get("modifiedAt")
        or node.get("lastModified")
        or node.get("modified")
        or node.get("lastModificationDate")
    )
    if modified_at is not None:
        modified_at = str(modified_at)
    read_only_flag = node.get("readOnly")
    if not isinstance(read_only_flag, bool):
        read_only_flag = None
    return DmsItem(
        id=edocat_nodes.node_uuid(node) or name,
        name=name,
        path=exposed_path,
        is_folder=edocat_nodes.is_folder_node(node),
        size=size,
        mime_type=str(node.get("mimeType")) if node.get("mimeType") else None,
        modified_at=modified_at,
        is_read_only=read_only_flag,
    )


def copy_payload(
    source_node: dict,
    parent: str,
    name: str,
    folder_node_type: str,
    document_node_type: str,
) -> dict[str, object]:
    is_folder = edocat_nodes.is_folder_node(source_node)
    payload: dict[str, object] = {
        "path": parent.lstrip("/"),
        "name": name,
        "nodeType": folder_node_type if is_folder else document_node_type,
    }
    if not is_folder:
        if isinstance(source_node.get("content"), str):
            payload["content"] = source_node.get("content")
        if source_node.get("mimeType"):
            payload["mimeType"] = source_node.get("mimeType")
    return payload
