from __future__ import annotations

from collections.abc import Callable

from dms_provider_bridge.models.item import DmsItem
from dms_provider_bridge.providers import edocat_nodes


def _int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value >= 0 and value.is_integer() else None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.isdecimal():
            return int(stripped)
    return None


def _extract_size(node: dict) -> int | None:
    candidates: list[object] = [
        node.get("size"),
        node.get("fileSize"),
        node.get("contentSize"),
        node.get("contentLength"),
        node.get("length"),
        node.get("bytes"),
        node.get("sizeInBytes"),
    ]

    content = node.get("content")
    if isinstance(content, dict):
        candidates.extend(
            [
                content.get("size"),
                content.get("fileSize"),
                content.get("contentSize"),
                content.get("contentLength"),
                content.get("length"),
                content.get("bytes"),
                content.get("sizeInBytes"),
            ]
        )

    for property_key in ("props", "properties", "metadata"):
        properties = node.get(property_key)
        if isinstance(properties, dict):
            candidates.extend(
                [
                    properties.get("size"),
                    properties.get("fileSize"),
                    properties.get("contentSize"),
                    properties.get("contentLength"),
                    properties.get("length"),
                    properties.get("bytes"),
                    properties.get("sizeInBytes"),
                    properties.get("cm:content.size"),
                    properties.get("cm:content.sizeInBytes"),
                ]
            )

    for candidate in candidates:
        size = _int_value(candidate)
        if size is not None:
            return size
    return None


def _string_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _extract_string(node: dict, keys: tuple[str, ...]) -> str | None:
    containers: list[dict] = [node]
    for property_key in ("props", "properties", "metadata"):
        properties = node.get(property_key)
        if isinstance(properties, dict):
            containers.append(properties)

    for container in containers:
        for key in keys:
            value = _string_value(container.get(key))
            if value is not None:
                return value
    return None


def _extract_version_label(node: dict) -> str | None:
    return _extract_string(
        node,
        (
            "cm:versionLabel",
            "versionLabel",
            "version_label",
            "version",
            "revision",
        ),
    )


def _extract_version_type(node: dict) -> str | None:
    return _extract_string(
        node,
        (
            "cm:versionType",
            "versionType",
            "version_type",
            "versionKind",
            "versionMode",
        ),
    )


def item_from_node(node: dict, fallback_path: str, public_path: Callable[[str], str]) -> DmsItem:
    node_path = str(node.get("_normalized_path") or "") or fallback_path
    exposed_path = public_path(node_path)
    name = str(node.get("name") or node_path.rstrip("/").split("/")[-1] or "/")
    size = _extract_size(node)
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
        version_label=_extract_version_label(node),
        version_type=_extract_version_type(node),
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
