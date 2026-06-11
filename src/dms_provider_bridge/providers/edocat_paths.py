from __future__ import annotations


def browse_root(config: dict) -> str:
    root = str(config.get("doc_library", "/deals")).strip() or "/deals"
    if not root.startswith("/"):
        root = f"/{root}"
    return root.rstrip("/") or "/"


def resolve_path(path: str, root: str) -> str:
    normalized = path.strip() or "/"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"

    if normalized == "/":
        return root
    if normalized == root or normalized.startswith(f"{root}/"):
        return normalized
    return f"{root}{normalized}"


def public_path(path: str, root: str) -> str:
    normalized = (path or "").strip() or "/"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    normalized = normalized.rstrip("/") or "/"

    if normalized == root:
        return "/"
    if root != "/" and normalized.startswith(f"{root}/"):
        value = normalized[len(root):]
        return value if value.startswith("/") else f"/{value}"
    return normalized


def parent_and_name(path: str, root: str) -> tuple[str, str]:
    resolved = resolve_path(path, root).rstrip("/") or "/"
    if resolved == "/":
        return "/", ""
    parent = resolved.rsplit("/", 1)[0] or "/"
    name = resolved.split("/")[-1]
    return parent, name


def normalize_node_path(node: dict) -> str:
    node_path = str(node.get("path") or "").strip()
    node_name = str(node.get("name") or "").strip()

    if node_path and not node_path.startswith("/"):
        node_path = f"/{node_path}"

    normalized_path = node_path.rstrip("/") or "/" if node_path else ""
    if not node_name:
        return normalized_path

    if normalized_path:
        last_segment = normalized_path.split("/")[-1] if normalized_path != "/" else ""
        if last_segment == node_name:
            return normalized_path
        if normalized_path == "/":
            return f"/{node_name}"
        return f"{normalized_path}/{node_name}"

    return f"/{node_name}"


def find_exact_node(nodes: list[dict], resolved_path: str) -> dict | None:
    normalized_target = resolved_path.rstrip("/") or "/"
    target_parent = normalized_target.rsplit("/", 1)[0] or "/"
    target_name = normalized_target.split("/")[-1] or "/"

    for node in nodes:
        if normalize_node_path(node) == normalized_target:
            return node

    for node in nodes:
        if str(node.get("name") or "") != target_name:
            continue
        node_path = normalize_node_path(node)
        node_parent = node_path.rsplit("/", 1)[0] or "/" if node_path else ""
        if node_parent == target_parent:
            return node

    return None
