from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import dms_provider_bridge.app.routes.config as config_routes
from dms_provider_bridge.app.server import create_app
from dms_provider_bridge.models.bridge import WfxResponse


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _use_repo_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    repo_config = Path(__file__).resolve().parents[1] / "config"
    user_config = tmp_path / "user-config"
    user_config.mkdir()
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(repo_config))
    monkeypatch.setenv("DMS_PROVIDER_USER_CONFIG_DIR", str(user_config))


def test_config_home_links_sections() -> None:
    client = TestClient(create_app())

    response = client.get("/config")

    assert response.status_code == 200
    assert "/docs" in response.text
    assert "/config/reload" in response.text
    assert "/config/bridge" in response.text
    assert "/config/providers" in response.text
    assert "/config/drivers" in response.text
    assert "/config/connections" in response.text


def test_config_reload_clears_provider_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(config_routes, "reload_connection_runtime_cache", lambda: calls.append("reload"))
    client = TestClient(create_app())

    response = client.get("/config/reload")

    assert response.status_code == 200
    assert calls == ["reload"]
    assert "Configuration cache was reloaded" in response.text


def test_config_reload_post_returns_audit_and_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    monkeypatch.setattr(config_routes, "reload_connection_runtime_cache", lambda: calls.append("reload"))
    monkeypatch.setattr(
        config_routes,
        "audit_connection_runtime",
        lambda: {
            "ok": True,
            "runtime_registry": {
                "wfx_connections": ["alfresco"],
                "available_drivers": ["alfresco"],
            },
        },
    )
    client = TestClient(create_app())

    response = client.post("/config/reload")

    assert response.status_code == 200
    payload = response.json()
    assert calls == ["reload"]
    assert payload["ok"] is True
    assert payload["message"] == "Configuration cache was reloaded."
    assert payload["audit"]["ok"] is True
    assert payload["registry"]["wfx_connections"] == ["alfresco"]
    assert payload["registry"]["available_drivers"] == ["alfresco"]


def test_config_audit_shows_connection_runtime_status() -> None:
    client = TestClient(create_app())

    response = client.get("/config/audit")

    assert response.status_code == 200
    assert "Connection runtime audit passed" in response.text
    assert "alfresco:/" in response.text
    assert "edocat:/" in response.text
    assert "Runtime Driver" in response.text
    assert "WFX connections" in response.text


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
    assert "TC VFS Contract" in response.text


def test_config_bridge_is_read_only() -> None:
    client = TestClient(create_app())

    response = client.get("/config/bridge")

    assert response.status_code == 200
    assert "bridge.json" in response.text
    assert "/config/bridge/bridge.json" in response.text
    assert "READ-ONLY CONFIG" in response.text
    assert "Bridge config controls the local bridge service" in response.text
    assert "when you know exactly what you are doing" in response.text

    file_response = client.get("/config/bridge/bridge.json")

    assert file_response.status_code == 200
    assert "readonly" in file_response.text
    assert "READ ONLY" in file_response.text
    assert "Bridge config controls the local bridge service" in file_response.text


def test_config_driver_json_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/config/drivers/driver.json/json")

    assert response.status_code == 200
    payload = response.json()
    assert payload["section"] == "drivers"
    assert payload["file"] == "driver.json"
    assert payload["read_only"] is True
    assert payload["data"]["key"] == "driver_name"


def test_config_connections_table_shows_driver_and_mount() -> None:
    client = TestClient(create_app())

    response = client.get("/config/connections")

    assert response.status_code == 200
    assert "<th>Driver</th>" in response.text
    assert "<th>Mount</th>" in response.text
    assert "<th>Actions</th>" in response.text
    assert "alfresco:/" in response.text
    assert ">alfresco</td>" in response.text
    assert "/config/connections/alfresco.json/delete" in response.text
    assert "/config/connections/connection.json/delete" not in response.text


def test_config_connection_editor_shows_test_link() -> None:
    client = TestClient(create_app())

    response = client.get("/config/connections/alfresco.json")

    assert response.status_code == 200
    assert "/config/connections/alfresco.json/test" in response.text
    assert "/config/connections/alfresco.json/delete" in response.text


def test_config_drivers_table_shows_connections() -> None:
    client = TestClient(create_app())

    response = client.get("/config/drivers")

    assert response.status_code == 200
    assert "<th>Connections</th>" in response.text
    assert "<th>Actions</th>" in response.text
    assert "alfresco" in response.text
    assert "/config/drivers/alfresco.json/delete" in response.text
    assert "/config/drivers/driver.json/delete" not in response.text


def test_config_connection_test_loads_runtime_config() -> None:
    client = TestClient(create_app())

    response = client.get("/config/connections/alfresco.json/test")

    assert response.status_code == 200
    assert "Connection runtime configuration was loaded successfully" in response.text
    assert "Connection OK" in response.text
    assert "alfresco:/" in response.text
    assert "Auth scheme" in response.text
    assert "ticket" in response.text
    assert "Live List Root" in response.text
    assert "Auth JSON is used only for this request and is not saved." in response.text


def test_config_connection_live_test_lists_root(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def _list_path(path, auth):
        calls.append((path, auth.username))
        return WfxResponse(ok=True, data={"items": [{"name": "Folder"}]})

    monkeypatch.setattr(config_routes, "list_path", _list_path)
    client = TestClient(create_app())

    response = client.post(
        "/config/connections/alfresco.json/test/live",
        data={
            "mount": "alfresco:/",
            "auth_json": json.dumps({"mode": "credentials", "username": "user", "password": "secret"}),
        },
    )

    assert response.status_code == 200
    assert "Live list root succeeded." in response.text
    assert "Items" in response.text
    assert ">1</td>" in response.text
    assert calls == [("alfresco:/", "user")]


def test_config_connection_live_test_reports_auth_json_error() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/config/connections/alfresco.json/test/live",
        data={"mount": "alfresco:/", "auth_json": "{}"},
    )

    assert response.status_code == 200
    assert "Live list root failed." in response.text


def test_config_test_rejects_non_connection_section() -> None:
    client = TestClient(create_app())

    response = client.get("/config/drivers/alfresco.json/test")

    assert response.status_code == 400


def test_config_new_driver_page_uses_template() -> None:
    client = TestClient(create_app())

    response = client.get("/config/drivers/new")

    assert response.status_code == 200
    assert "New file will be created from template driver.json" in response.text
    assert "new_driver" in response.text
    assert "driver_name" not in response.text
    assert "<form" in response.text
    assert "Create" in response.text


def test_config_template_editor_is_read_only() -> None:
    client = TestClient(create_app())

    response = client.get("/config/drivers/driver.json")

    assert response.status_code == 200
    assert "TEMPLATE READ ONLY" in response.text
    assert "readonly" in response.text
    assert "disabled" in response.text
    assert "/config/drivers/driver.json/delete" not in response.text


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
            "mount": "test_connection:/",
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


def test_config_save_reloads_provider_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_config = Path(__file__).resolve().parents[1] / "config"
    config_dir = tmp_path / "config"
    shutil.copytree(repo_config, config_dir)
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(config_dir))
    calls = []
    monkeypatch.setattr(config_routes, "reload_connection_runtime_cache", lambda: calls.append("reload"))
    client = TestClient(create_app())
    payload = {
        "key": "reload_connection",
        "reload_connection": {
            "display_name": "Reload Connection",
            "driver": "alfresco",
            "mount": "reload_connection:/",
        },
    }

    response = client.post(
        "/config/connections/save",
        data={"file_name": "", "payload": json.dumps(payload)},
    )

    assert response.status_code == 200
    assert calls == ["reload"]


def test_config_save_new_connection_requires_overwrite_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_config = Path(__file__).resolve().parents[1] / "config"
    config_dir = tmp_path / "config"
    shutil.copytree(repo_config, config_dir)
    existing = config_dir / "connections" / "existing.json"
    existing.write_text('{"key": "existing", "existing": {"display_name": "Old"}}', encoding="utf-8")
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(config_dir))
    client = TestClient(create_app())
    payload = {
        "key": "existing",
        "existing": {
            "display_name": "New",
            "driver": "alfresco",
            "mount": "existing:/",
        },
    }

    response = client.post(
        "/config/connections/save",
        data={"file_name": "", "payload": json.dumps(payload)},
    )

    assert response.status_code == 200
    assert "Confirm overwrite" in response.text
    assert "Overwrite" in response.text
    assert json.loads(existing.read_text(encoding="utf-8"))["existing"]["display_name"] == "Old"


def test_config_save_new_connection_overwrites_after_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_config = Path(__file__).resolve().parents[1] / "config"
    config_dir = tmp_path / "config"
    shutil.copytree(repo_config, config_dir)
    existing = config_dir / "connections" / "existing.json"
    existing.write_text('{"key": "existing", "existing": {"display_name": "Old"}}', encoding="utf-8")
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(config_dir))
    client = TestClient(create_app())
    payload = {
        "key": "existing",
        "existing": {
            "display_name": "New",
            "driver": "alfresco",
            "mount": "existing:/",
        },
    }

    response = client.post(
        "/config/connections/save",
        data={"file_name": "", "payload": json.dumps(payload), "overwrite": "true"},
    )

    assert response.status_code == 200
    assert "Saved existing.json" in response.text
    assert json.loads(existing.read_text(encoding="utf-8"))["existing"]["display_name"] == "New"


def test_config_save_existing_file_can_change_key_to_new_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_config = Path(__file__).resolve().parents[1] / "config"
    config_dir = tmp_path / "config"
    shutil.copytree(repo_config, config_dir)
    source = config_dir / "connections" / "old_name.json"
    source.write_text('{"key": "old_name", "old_name": {"driver": "alfresco"}}', encoding="utf-8")
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(config_dir))
    client = TestClient(create_app())
    payload = {"key": "new_name", "new_name": {"driver": "alfresco", "mount": "new_name:/"}}

    response = client.post(
        "/config/connections/save",
        data={"file_name": "old_name.json", "payload": json.dumps(payload)},
    )

    assert response.status_code == 200
    assert (config_dir / "connections" / "new_name.json").exists()
    assert source.exists()


def test_config_delete_confirm_shows_editable_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_config = Path(__file__).resolve().parents[1] / "config"
    config_dir = tmp_path / "config"
    shutil.copytree(repo_config, config_dir)
    target = config_dir / "connections" / "delete_me.json"
    target.write_text('{"key": "delete_me", "delete_me": {"driver": "alfresco", "mount": "delete_me:/"}}', encoding="utf-8")
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(config_dir))
    client = TestClient(create_app())

    response = client.get("/config/connections/delete_me.json/delete")

    assert response.status_code == 200
    assert "Delete config file delete_me.json?" in response.text
    assert '<form method="post" action="/config/connections/delete_me.json/delete">' in response.text


def test_config_delete_removes_editable_file_and_reloads_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo_config = Path(__file__).resolve().parents[1] / "config"
    config_dir = tmp_path / "config"
    shutil.copytree(repo_config, config_dir)
    target = config_dir / "connections" / "delete_me.json"
    target.write_text('{"key": "delete_me", "delete_me": {"driver": "alfresco", "mount": "delete_me:/"}}', encoding="utf-8")
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(config_dir))
    calls = []
    monkeypatch.setattr(config_routes, "reload_connection_runtime_cache", lambda: calls.append("reload"))
    client = TestClient(create_app())

    response = client.post("/config/connections/delete_me.json/delete")

    assert response.status_code == 200
    assert "Deleted delete_me.json." in response.text
    assert not target.exists()
    assert calls == ["reload"]


def test_config_delete_rejects_read_only_template() -> None:
    client = TestClient(create_app())

    response = client.post("/config/drivers/driver.json/delete")

    assert response.status_code == 403


def test_config_delete_rejects_provider_abc() -> None:
    client = TestClient(create_app())

    response = client.post("/config/providers/provider.json/delete")

    assert response.status_code == 403


def test_config_save_connection_rejects_unknown_driver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_config = Path(__file__).resolve().parents[1] / "config"
    config_dir = tmp_path / "config"
    shutil.copytree(repo_config, config_dir)
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(config_dir))
    client = TestClient(create_app())
    payload = {"key": "bad_driver", "bad_driver": {"driver": "missing_driver", "mount": "bad_driver:/"}}

    response = client.post(
        "/config/connections/save",
        data={"file_name": "", "payload": json.dumps(payload)},
    )

    assert response.status_code == 200
    assert "Validation failed" in response.text
    assert "Connection driver &#x27;missing_driver&#x27; does not exist." in response.text
    assert not (config_dir / "connections" / "bad_driver.json").exists()


def test_config_save_connection_requires_mount(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_config = Path(__file__).resolve().parents[1] / "config"
    config_dir = tmp_path / "config"
    shutil.copytree(repo_config, config_dir)
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(config_dir))
    client = TestClient(create_app())
    payload = {"key": "missing_mount", "missing_mount": {"driver": "alfresco"}}

    response = client.post(
        "/config/connections/save",
        data={"file_name": "", "payload": json.dumps(payload)},
    )

    assert response.status_code == 200
    assert "Connection field &#x27;mount&#x27; is required." in response.text
    assert not (config_dir / "connections" / "missing_mount.json").exists()


def test_config_save_connection_rejects_duplicate_mount(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo_config = Path(__file__).resolve().parents[1] / "config"
    config_dir = tmp_path / "config"
    shutil.copytree(repo_config, config_dir)
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(config_dir))
    client = TestClient(create_app())
    payload = {"key": "duplicate_mount", "duplicate_mount": {"driver": "alfresco", "mount": "alfresco:/"}}

    response = client.post(
        "/config/connections/save",
        data={"file_name": "", "payload": json.dumps(payload)},
    )

    assert response.status_code == 200
    assert "Connection mount &#x27;alfresco:/&#x27; is already used by alfresco.json." in response.text
    assert not (config_dir / "connections" / "duplicate_mount.json").exists()


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
