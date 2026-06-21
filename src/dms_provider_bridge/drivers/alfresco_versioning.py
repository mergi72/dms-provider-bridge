from __future__ import annotations


def version_label_from_entry(entry: dict | None) -> str | None:
    if not isinstance(entry, dict):
        return None
    props = entry.get("properties")
    if isinstance(props, dict):
        for key in ("cm:versionLabel", "versionLabel"):
            value = props.get(key)
            if value is not None:
                return str(value)
    for key in ("versionLabel", "version"):
        value = entry.get(key)
        if value is not None:
            return str(value)
    return None


def version_type_from_entry(entry: dict | None) -> str | None:
    if not isinstance(entry, dict):
        return None
    props = entry.get("properties")
    if isinstance(props, dict):
        value = props.get("cm:versionType") or props.get("versionType")
        if value is not None:
            return str(value)
    return None


def user_name_from_entry(entry: dict | None, field: str) -> str | None:
    if not isinstance(entry, dict):
        return None
    value = entry.get(field)
    if isinstance(value, dict):
        for key in ("id", "displayName"):
            user_value = value.get(key)
            if user_value is not None:
                return str(user_value)
    if value is not None:
        return str(value)
    return None


def audit_from_entry(entry: dict | None) -> dict[str, object | None]:
    if not isinstance(entry, dict):
        return {
            "created_at": None,
            "created_by": None,
            "modified_at": None,
            "modified_by": None,
        }
    return {
        "created_at": str(entry.get("createdAt")) if entry.get("createdAt") is not None else None,
        "created_by": user_name_from_entry(entry, "createdByUser"),
        "modified_at": str(entry.get("modifiedAt")) if entry.get("modifiedAt") is not None else None,
        "modified_by": user_name_from_entry(entry, "modifiedByUser"),
    }


def versioning_choice(versioning: dict | None) -> tuple[bool, str | None] | None:
    if not isinstance(versioning, dict):
        return None
    mode = str(versioning.get("mode") or "").strip().lower()
    if mode != "version":
        return None

    major_version = bool(versioning.get("majorVersion", False))
    comment = versioning.get("comment")
    return major_version, str(comment) if isinstance(comment, str) and comment.strip() else None


def existing_upload_metadata(connection_name: str, target_destination: str, existing: dict) -> dict[str, object]:
    audit = audit_from_entry(existing)
    return {
        "action": "version_required",
        "connection": connection_name,
        "provider": connection_name,
        "path": target_destination,
        "name": str(existing.get("name") or target_destination.rstrip("/").split("/")[-1]),
        "node_id": str(existing.get("id") or ""),
        "current_version": version_label_from_entry(existing),
        "current_version_type": version_type_from_entry(existing),
        "current_created_at": audit["created_at"],
        "current_created_by": audit["created_by"],
        "current_modified_at": audit["modified_at"],
        "current_modified_by": audit["modified_by"],
        "versioning": {
            "mode": "version",
            "majorVersion": False,
            "comment_supported": True,
        },
    }
