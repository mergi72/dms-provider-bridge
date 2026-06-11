from __future__ import annotations

from urllib.parse import unquote, urlparse


def share_url_to_path(share_url: str) -> str:
    parsed = urlparse(share_url)
    fragment = parsed.fragment or ""
    if not fragment:
        raise ValueError("Share URL must contain a hash path (fragment).")

    fragment_path = fragment.split("?", 1)[0].strip()
    if not fragment_path:
        raise ValueError("Share URL fragment path is empty.")

    normalized = unquote(fragment_path).replace("\\", "/")
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized
