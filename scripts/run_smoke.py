from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


def _fail(message: str) -> None:
    raise RuntimeError(f"Bridge smoke failed: {message}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    src_root = repo_root / "src"
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))

    from dms_provider_bridge.app.server import create_app

    client = TestClient(create_app())

    health = client.get("/health")
    if health.status_code != 200:
        _fail(f"/health returned HTTP {health.status_code}")
    health_body = health.json()
    if health_body.get("status") != "ok":
        _fail("/health status is not ok")

    connections = client.get("/bridge/wfx/connections")
    if connections.status_code != 200:
        _fail(f"/bridge/wfx/connections returned HTTP {connections.status_code}")
    connections_body = connections.json()
    if not connections_body.get("ok"):
        _fail("/bridge/wfx/connections returned ok=false")
    connections_data = connections_body.get("data") or {}
    connection_names = connections_data.get("connection_names") or []
    if not connection_names:
        _fail("connection discovery returned no connections")

    root_listing = client.post("/bridge/wfx/list", json={"path": "/"})
    if root_listing.status_code != 200:
        _fail(f"/bridge/wfx/list connection root returned HTTP {root_listing.status_code}")
    root_listing_body = root_listing.json()
    if not root_listing_body.get("ok"):
        _fail(f"/bridge/wfx/list connection root returned ok=false: {root_listing_body.get('message')}")

    print("Bridge smoke passed: health/connection discovery contract is operational.")


if __name__ == "__main__":
    main()

