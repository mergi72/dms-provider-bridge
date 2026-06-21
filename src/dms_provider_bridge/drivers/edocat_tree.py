from __future__ import annotations

from collections.abc import Callable


def direct_child_nodes(
    nodes: list[dict],
    normalized_folder: str,
    normalize_node_path: Callable[[dict], str],
) -> list[dict]:
    direct_children: list[dict] = []
    seen_paths: set[str] = set()
    for node in nodes:
        child_path = normalize_node_path(node)
        if not child_path or child_path == normalized_folder:
            continue
        child_parent = child_path.rsplit("/", 1)[0] or "/"
        if child_parent != normalized_folder or child_path in seen_paths:
            continue
        direct_children.append(node)
        seen_paths.add(child_path)
    return direct_children


def descendant_paths(
    nodes: list[dict],
    normalized_folder: str,
    normalize_node_path: Callable[[dict], str],
) -> set[str]:
    paths: set[str] = set()
    for child in nodes:
        child_path = normalize_node_path(child)
        if not child_path or child_path == normalized_folder:
            continue
        if child_path.startswith(f"{normalized_folder}/"):
            paths.add(child_path)
    return paths


def child_destination_path(destination_folder_path: str, child_source_path: str) -> str:
    child_name = child_source_path.rsplit("/", 1)[-1]
    if destination_folder_path == "/":
        return f"/{child_name}"
    return f"{destination_folder_path.rstrip('/')}/{child_name}"
