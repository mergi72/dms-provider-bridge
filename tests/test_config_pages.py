from __future__ import annotations

import json
import shutil
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
    assert payload["read_only"] is True
    assert payload["data"]["key"] == "driver_name"


def test_config_new_driver_page_uses_template() -> None:
    client = TestClient(create_app())

    response = client.get("/config/drivers/new")

    assert response.status_code == 200
    assert "New file will be created from template driver.json" in response.text
    assert "<form" in response.text
    assert "Create" in response.text


def test_config_template_editor_is_read_only() -> None:
    client = TestClient(create_app())

    response = client.get("/config/drivers/driver.json")

    assert response.status_code == 200
    assert "TEMPLATE READ ONLY" in response.text
    assert "readonly" in response.text
    assert "disabled" in response.text


def test_config_templates_are_visible_when_machine_section_is_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_dir = tmp_path / "config"
    (config_dir / "drivers").mkdir(parents=True)
    (config_dir / "connections").mkdir(parents=True)
    (config_dir / "providers").mkdir(parents=True)
    (config_dir / "bridge.json").write_text(
        '{"paths":{"providers":"providers","drivers":"drivers","connections":"connections"}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(config_dir))
    client = TestClient(create_app())

    section_response = client.get("/config/connections")
    template_response = client.get("/config/connections/connection.json")

    assert section_response.status_code == 200
    assert "connection.json" in section_response.text
    assert "TEMPLATE READ ONLY" in section_response.text
    assert template_response.status_code == 200
    assert "connection_name" in template_response.text


def test_config_save_new_connection_creates_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_config = Path(__file__).resolve().parents[1] / "config"
    config_dir = tmp_path / "config"
    shutil.copytree(repo_config, config_dir)
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(config_dir))
    client = TestClient(create_app())
    payload = {
        "key": "test_connection",
        "test_connection": {
            "display_name": "Test Connection",
            "driver": "alfresco",
        },
    }

    response = client.post(
        "/config/connections/save",
        data={"file_name": "", "payload": json.dumps(payload)},
    )

    assert response.status_code == 200
    created = config_dir / "connections" / "test_connection.json"
    assert created.exists()
    assert json.loads(created.read_text(encoding="utf-8"))["key"] == "test_connection"
    assert "Saved test_connection.json" in response.text


def test_config_save_rejects_template_overwrite() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/config/drivers/save",
        data={"file_name": "driver.json", "payload": '{"key": "driver_name"}'},
    )

    assert response.status_code == 403


def test_config_save_rejects_template_key() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/config/drivers/save",
        data={"file_name": "", "payload": '{"key": "driver_name"}'},
    )

    assert response.status_code == 400


def test_config_rejects_path_traversal() -> None:
    client = TestClient(create_app())

    response = client.get("/config/drivers/..%5Cbridge.json")

    assert response.status_code == 400
