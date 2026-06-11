from __future__ import annotations


def node_type_config(config: dict) -> dict[str, str]:
    value = config.get("nodeType", {})
    return value if isinstance(value, dict) else {}


def document_node_type(config: dict) -> str:
    node_type_cfg = node_type_config(config)
    return (
        node_type_cfg.get("baseDoc")
        or node_type_cfg.get("file")
        or "ctbd:baseDoc"
    )


def folder_node_type(config: dict) -> str:
    node_type_cfg = node_type_config(config)
    return (
        node_type_cfg.get("folder")
        or node_type_cfg.get("baseFolder")
        or "com.onlio.edocat.BaseFolder"
    )


def copy_max_nodes(config: dict) -> int:
    copy_cfg = config.get("copy", {})
    if isinstance(copy_cfg, dict):
        value = copy_cfg.get("maxNodes")
        if isinstance(value, int) and value > 0:
            return value
    return 200


def delete_max_nodes(config: dict) -> int:
    delete_cfg = config.get("delete", {})
    if isinstance(delete_cfg, dict):
        value = delete_cfg.get("maxNodes")
        if isinstance(value, int) and value > 0:
            return value
    return copy_max_nodes(config)


def download_max_bytes(config: dict) -> int:
    download_cfg = config.get("download", {})
    if isinstance(download_cfg, dict):
        value = download_cfg.get("maxBase64Bytes")
        if isinstance(value, int) and value > 0:
            return value

    transfer_cfg = config.get("transfer", {})
    if isinstance(transfer_cfg, dict):
        value = transfer_cfg.get("maxBase64Bytes")
        if isinstance(value, int) and value > 0:
            return value
    return 20 * 1024 * 1024


def download_max_nodes(config: dict) -> int:
    download_cfg = config.get("download", {})
    if isinstance(download_cfg, dict):
        value = download_cfg.get("maxNodes")
        if isinstance(value, int) and value > 0:
            return value

    transfer_cfg = config.get("transfer", {})
    if isinstance(transfer_cfg, dict):
        value = transfer_cfg.get("maxNodes")
        if isinstance(value, int) and value > 0:
            return value
    return 500


def download_zip_endpoint(config: dict) -> str | None:
    download_cfg = config.get("download", {})
    if not isinstance(download_cfg, dict):
        return None
    endpoint = download_cfg.get("zipEndpoint")
    if isinstance(endpoint, str):
        endpoint = endpoint.strip()
        if endpoint:
            return endpoint
    return None


def download_zip_method(config: dict) -> str:
    download_cfg = config.get("download", {})
    if isinstance(download_cfg, dict):
        method = str(download_cfg.get("zipMethod") or "POST").strip().upper()
        if method in {"GET", "POST"}:
            return method
    return "POST"


def download_zip_content_type(config: dict) -> str:
    download_cfg = config.get("download", {})
    if isinstance(download_cfg, dict):
        content_type = download_cfg.get("zipContentType")
        if isinstance(content_type, str) and content_type.strip():
            return content_type.strip()
    return "application/zip"


def download_zip_url(base_url: str, api_root: str, endpoint: str) -> str:
    if endpoint.startswith("http://") or endpoint.startswith("https://"):
        return endpoint
    normalized_base_url = (base_url or "").rstrip("/")
    if not normalized_base_url:
        return endpoint
    if endpoint.startswith("/"):
        return f"{normalized_base_url}{endpoint}"
    normalized_api_root = (api_root or "").strip("/")
    prefix = f"/{normalized_api_root}" if normalized_api_root else ""
    return f"{normalized_base_url}{prefix}/{endpoint}"


def download_zip_payload(config: dict, node_uuid: str) -> dict[str, object]:
    download_cfg = config.get("download", {})
    if isinstance(download_cfg, dict):
        payload_mode = str(download_cfg.get("zipPayloadMode") or "uuids").strip().lower()
        if payload_mode == "uuid":
            return {"uuid": node_uuid}
        if payload_mode == "path":
            return {"path": node_uuid}
    return {"uuids": [node_uuid]}
