from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi.testclient import TestClient

from edocat_bridge.app.server import create_app


def _fail(message: str) -> None:
    raise RuntimeError(f"Bridge smoke failed: {message}")


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    fso_config_path = repo_root / "config" / "fso.json"

    if not fso_config_path.exists():
        _fail(f"Missing config file: {fso_config_path}")

    original_config = fso_config_path.read_bytes()
    repo_root_posix = repo_root.as_posix()
    test_path = f"fso:{repo_root_posix}"
    user_name = os.getenv("USER") or os.getenv("USERNAME") or "ci-runner"

    try:
        fso_config_path.write_text(
            json.dumps(
                {
                    "key": "fso",
                    "fso": {
                        "allowedRoots": [repo_root_posix],
                    },
                }
            ),
            encoding="utf-8",
        )

        client = TestClient(create_app())

        health = client.get("/health")
        if health.status_code != 200:
            _fail(f"/health returned HTTP {health.status_code}")
        health_body = health.json()
        if health_body.get("status") != "ok":
            _fail("/health status is not ok")

        providers = client.get("/bridge/wfx/providers")
        if providers.status_code != 200:
            _fail(f"/bridge/wfx/providers returned HTTP {providers.status_code}")
        providers_body = providers.json()
        if not providers_body.get("ok"):
            _fail("/bridge/wfx/providers returned ok=false")
        providers_data = providers_body.get("data") or {}
        provider_names = providers_data.get("providers") or []
        if "fso" not in provider_names:
            _fail("fso provider not present in provider discovery")

        listing = client.post(
            "/bridge/wfx/list",
            json={
                "path": test_path,
                "auth": {"mode": "winuser", "win_user": user_name},
            },
        )
        if listing.status_code != 200:
            _fail(f"/bridge/wfx/list returned HTTP {listing.status_code}")
        listing_body = listing.json()
        if not isinstance(listing_body.get("ok"), bool):
            _fail("/bridge/wfx/list response is missing boolean ok")
        if not listing_body.get("ok"):
            _fail(f"/bridge/wfx/list returned ok=false: {listing_body.get('message')}")

        print("Bridge smoke passed: health/providers/list contract is operational.")
    finally:
        fso_config_path.write_bytes(original_config)


if __name__ == "__main__":
    main()
