from __future__ import annotations


def node_uuid(node: dict | None) -> str:
    if not isinstance(node, dict):
        return ""
    return str(node.get("uuid") or node.get("id") or "")


def is_folder_node(node: dict | None) -> bool:
    if not isinstance(node, dict):
        return False
    node_type = str(node.get("nodeType") or "").lower()
    return node_type.endswith("folder") or node_type.endswith("basefolder")
