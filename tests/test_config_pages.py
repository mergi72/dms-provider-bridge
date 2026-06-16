from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dms_provider_bridge.app.server import create_app


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _use_repo_config(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_config = Path(__file__).resolve().parents[1] / "config"
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(repo_config))
    monkeypatch.delenv("DMS_PROVIDER_USER_CONFIG_DIR", raising=False)


def test_config_home_links_sections() -> None:
    client = TestClient(create_app())

    response = client.get("/config")

    assert response.status_code == 200
    assert "/docs" in response.text
    assert "/config/providers" in response.text
    assert "/config/drivers" in response.text
    assert "/config/connections" in response.text


def test_docs_openapi_links_config() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/config" in response.json()["info"]["description"]

    docs_response = client.get("/docs")

    assert docs_response.status_code == 200
    assert 'href="/config"' in docs_response.text


def test_config_providers_is_read_only() -> None:
    client = TestClient(create_app())

    response = client.get("/config/providers/provider.json")

    assert response.status_code == 200
    assert "readonly" in response.text
    assert "Provider ABC" in response.text


def test_config_driver_json_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/config/drivers/driver.json/json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["section"] == "drivers"
    assert payload["file"] == "driver.json"
    assert payload["read_only"] is False
    assert payload["data"]["key"] == "driver_name"


def test_config_rejects_path_traversal() -> None:
    client = TestClient(create_app())

    response = client.get("/config/drivers/..%5Cbridge.json")

    assert response.status_code == 400
