from __future__ import annotations


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
