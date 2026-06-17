from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dms_provider_bridge.app.server import create_app
from dms_provider_bridge.app.routes import bridge as bridge_routes
from dms_provider_bridge.models.bridge import WfxResponse
from dms_provider_bridge.services import bridge_service


pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _use_repo_config(monkeypatch: pytest.MonkeyPatch) -> None:
    repo_config = Path(__file__).resolve().parents[1] / "config"
    monkeypatch.setenv("DMS_PROVIDER_MACHINE_CONFIG_DIR", str(repo_config))
    monkeypatch.delenv("DMS_PROVIDER_USER_CONFIG_DIR", raising=False)


def _auth() -> dict[str, str]:
    return {"mode": "winuser", "win_user": "DOMAIN\\tester"}


def _share_url() -> str:
    return (
        "https://example.com/share/page/site/deals/documentlibrary"
        "#/Team%20Documents/Projects/Upload?page=1"
    )


def _source_file_path() -> str:
    return (
        "/Team Documents/Projects/Upload/sample.txt"
    )


def _target_file_path(name: str) -> str:
    return (
        f"/Team Documents/Projects/Upload/{name}"
    )


def _target_folder_path(name: str) -> str:
    return (
        f"/Team Documents/Projects/Upload/{name}"
    )


def test_health() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_bridge_providers() -> None:
    client = TestClient(create_app())
    response = client.get("/bridge/wfx/providers")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert set(body["data"]["providers"]) >= {"edocat", "alfresco"}
    assert body["data"]["default_provider"] is None or body["data"]["default_provider"] in body["data"]["providers"]
    assert body["providers"] == body["data"]["providers"]
    assert body["default_provider"] == body["data"]["default_provider"]


def test_bridge_provider_detail_returns_auth_and_capabilities() -> None:
    client = TestClient(create_app())
    response = client.get("/bridge/wfx/providers/alfresco")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["name"] == "alfresco"
    assert body["data"]["kind"] == "connection"
    assert body["data"]["driver"] == "alfresco"
    assert body["data"]["mount"] == "alfresco:/"
    assert body["data"]["display_name"] == "Alfresco"
    assert body["data"]["enabled"] is True
    assert body["data"]["auth"] == {
        "mode": "windows",
        "target": "tc-wfx/bridge",
        "required": True,
    }
    assert body["data"]["capabilities"] == {
        "list": True,
        "stat": True,
        "download": True,
        "upload": True,
        "mkdir": True,
        "delete": True,
        "rename": True,
        "copy": True,
    }
    assert body["data"]["versioning"] == {
        "supported": True,
        "existing_upload": "version_required",
        "modes": ["version"],
        "majorVersion": False,
        "comment_supported": True,
    }
    assert body["metadata"]["operation"] == "provider_detail"


def test_bridge_provider_audit_returns_connection_runtime_status() -> None:
    client = TestClient(create_app())
    response = client.get("/bridge/wfx/providers/audit")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["ok"] is True
    by_name = {item["name"]: item for item in body["data"]["connections"]}
    assert by_name["alfresco"]["driver"] == "alfresco"
    assert by_name["alfresco"]["mount"] == "alfresco:/"
    assert by_name["alfresco"]["runtime_driver"] == "alfresco"
    assert by_name["alfresco"]["runtime_mount"] == "alfresco:/"
    assert by_name["alfresco"]["issues"] == []
    assert body["metadata"]["operation"] == "providers_audit"


def test_openapi_upload_versioning_schema_is_typed() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    schemas = response.json()["components"]["schemas"]
    upload_schema = schemas["WfxUploadRequest"]
    versioning_ref = upload_schema["properties"]["versioning"]["anyOf"][0]["$ref"]
    assert versioning_ref == "#/components/schemas/UploadVersioning"
    versioning_schema = schemas["UploadVersioning"]
    assert set(versioning_schema["properties"]) == {"mode", "majorVersion", "comment"}
    assert versioning_schema["properties"]["mode"]["const"] == "version"
    assert versioning_schema["properties"]["mode"]["default"] == "version"
    assert versioning_schema["properties"]["majorVersion"]["default"] is False


def test_bridge_provider_detail_unknown_provider() -> None:
    client = TestClient(create_app())
    response = client.get("/bridge/wfx/providers/unknown")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == 1
    assert "not registered" in body["message"]


def test_bridge_stat_success_returns_http_200(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bridge_routes,
        "stat_path",
        lambda path, auth: WfxResponse(ok=True, data={"path": path}),
    )
    client = TestClient(create_app())

    response = client.post("/bridge/wfx/stat", json={"path": "edocat:/folder", "auth": _auth()})

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_bridge_stat_upstream_error_returns_upstream_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        bridge_routes,
        "stat_path",
        lambda path, auth: WfxResponse(
            ok=False,
            error_code=5,
            message="eDoCat query failed for /folder: HTTP 404.",
            metadata={"upstream_status_code": 404},
        ),
    )
    client = TestClient(create_app())

    response = client.post("/bridge/wfx/stat", json={"path": "edocat:/folder", "auth": _auth()})

    assert response.status_code == 404
    assert response.json()["ok"] is False


def test_bridge_root_list_returns_provider_folders_without_auth() -> None:
    client = TestClient(create_app())
    response = client.post("/bridge/wfx/list", json={"path": "/"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["provider"] == "bridge"
    assert body["data"]["path"] == "/"
    provider_names = {item["name"] for item in body["data"]["items"]}
    assert provider_names >= {"edocat", "alfresco"}
    assert all(item["is_folder"] is True for item in body["data"]["items"])
    assert body["metadata"]["provider_root"] is True


def test_bridge_root_list_returns_providers_when_default_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bridge_service, "get_default_connection_name", lambda: (_ for _ in ()).throw(RuntimeError("bad default")))
    client = TestClient(create_app())

    response = client.post("/bridge/wfx/list", json={"path": "/"})

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert {item["name"] for item in body["data"]["items"]} >= {"edocat", "alfresco"}
    assert body["metadata"]["default_provider"] is None


def test_resolve_share_url() -> None:
    client = TestClient(create_app())
    payload = {"share_url": _share_url(), "provider": "alfresco"}
    response = client.post("/bridge/wfx/resolve-share-url", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["path"].startswith("alfresco:/")


def test_browse_share_url_dry_run() -> None:
    client = TestClient(create_app())
    payload = {
        "share_url": _share_url(),
        "provider": "alfresco",
        "operation": "copy",
        "execute": False,
        "auth": _auth(),
        "provider_path_override": _source_file_path(),
        "destination_path_override": _target_file_path("sample-copy-dry-run.txt"),
    }
    response = client.post("/bridge/wfx/browse-share-url", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["executed"] is False
    assert body["metadata"]["operation"] == "browse-share-url:dry-run:copy"


def test_browse_share_url_move_dry_run() -> None:
    client = TestClient(create_app())
    payload = {
        "share_url": _share_url(),
        "provider": "alfresco",
        "operation": "move",
        "execute": False,
        "auth": _auth(),
        "provider_path_override": _source_file_path(),
        "destination_path_override": _target_file_path("sample-move-dry-run.txt"),
    }
    response = client.post("/bridge/wfx/browse-share-url", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["executed"] is False
    assert body["metadata"]["operation"] == "browse-share-url:dry-run:move"


def test_validate_alias_returns_dry_run_payload() -> None:
    client = TestClient(create_app())
    payload = {
        "share_url": _share_url(),
        "provider": "alfresco",
        "operation": "copy",
        "provider_path_override": _source_file_path(),
        "destination_path_override": _target_file_path("sample-copy-validate.txt"),
    }
    response = client.post("/bridge/wfx/browse-share-url-validate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["executed"] is False


def test_browse_share_url_upload_requires_file_name() -> None:
    client = TestClient(create_app())
    payload = {
        "share_url": _share_url(),
        "provider": "alfresco",
        "operation": "upload",
        "execute": False,
        "auth": _auth(),
        "destination_path_override": _target_folder_path("Upload"),
    }
    response = client.post("/bridge/wfx/browse-share-url", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["error_code"] == 4
    assert "file_name" in body["message"]


def test_core_wfx_operations_smoke() -> None:
    client = TestClient(create_app())
    auth = _auth()

    list_resp = client.post(
        "/bridge/wfx/list",
        json={"path": "alfresco:/contracts", "auth": auth},
    )
    stat_resp = client.post(
        "/bridge/wfx/stat",
        json={"path": "alfresco:/contracts/sample.txt", "auth": auth},
    )
    mkdir_resp = client.post(
        "/bridge/wfx/mkdir",
        json={"path": "alfresco:/contracts/new-folder", "auth": auth},
    )
    delete_resp = client.post(
        "/bridge/wfx/delete",
        json={"path": "alfresco:/contracts/sample.txt", "auth": auth},
    )
    copy_resp = client.post(
        "/bridge/wfx/copy",
        json={
            "source": "alfresco:/contracts/sample.txt",
            "destination": "alfresco:/contracts/sample-copy.txt",
            "auth": auth,
        },
    )
    move_resp = client.post(
        "/bridge/wfx/move",
        json={
            "source": "alfresco:/contracts/sample.txt",
            "destination": "alfresco:/contracts/sample-moved.txt",
            "auth": auth,
        },
    )
    download_resp = client.post(
        "/bridge/wfx/download",
        json={"path": "alfresco:/contracts/sample.txt", "auth": auth},
    )
    download_raw_resp = client.post(
        "/bridge/wfx/download-raw",
        json={"path": "alfresco:/contracts/sample.txt", "auth": auth},
    )
    upload_resp = client.post(
        "/bridge/wfx/upload",
        json={
            "destination": "alfresco:/contracts",
            "auth": auth,
            "file_name": "upload.txt",
            "content_base64": "dGVzdA==",
            "overwrite": True,
        },
    )

    for resp in [
        list_resp,
        stat_resp,
        mkdir_resp,
        delete_resp,
        copy_resp,
        move_resp,
        upload_resp,
    ]:
        assert resp.status_code == 200
        assert "ok" in resp.json()

    assert download_resp.status_code == 200
    assert "ok" in download_resp.json()
    assert download_raw_resp.status_code == 200


def test_bridge_copy_accepts_source_and_destination_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def _copy_path(source, destination, auth, source_auth=None, destination_auth=None, versioning=None):
        captured["source"] = source
        captured["destination"] = destination
        captured["auth"] = auth
        captured["source_auth"] = source_auth
        captured["destination_auth"] = destination_auth
        return WfxResponse(ok=True, data={"copied": True})

    monkeypatch.setattr(bridge_routes, "copy_path", _copy_path)
    client = TestClient(create_app())

    response = client.post(
        "/bridge/wfx/copy",
        json={
            "source": "edocat:/source.txt",
            "destination": "alfresco:/target.txt",
            "auth": {"mode": "credentials", "credential_id": "fallback"},
            "source_auth": {"mode": "credentials", "credential_id": "edocat-credential"},
            "destination_auth": {"mode": "credentials", "credential_id": "alfresco-credential"},
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured["source"] == "edocat:/source.txt"
    assert captured["destination"] == "alfresco:/target.txt"
    assert captured["auth"].credential_id == "fallback"
    assert captured["source_auth"].credential_id == "edocat-credential"
    assert captured["destination_auth"].credential_id == "alfresco-credential"


def test_bridge_copy_accepts_versioning(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def _copy_path(source, destination, auth, source_auth=None, destination_auth=None, versioning=None):
        captured["versioning"] = versioning
        return WfxResponse(ok=True, data={"copied": True})

    monkeypatch.setattr(bridge_routes, "copy_path", _copy_path)
    client = TestClient(create_app())

    response = client.post(
        "/bridge/wfx/copy",
        json={
            "source": "edocat:/source.txt",
            "destination": "alfresco:/target.txt",
            "auth": {"mode": "credentials", "credential_id": "fallback"},
            "versioning": {"mode": "version", "majorVersion": True, "comment": "copy"},
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert captured["versioning"].majorVersion is True
    assert captured["versioning"].comment == "copy"


def test_upload_raw_streams_file_via_source_path(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(create_app())

    def fake_upload_path(destination, file_name, auth, content_base64=None, source_path=None, overwrite=False):
        assert destination == "alfresco:/contracts"
        assert file_name == "upload.bin"
        assert content_base64 is None
        assert isinstance(source_path, str)
        with open(source_path, "rb") as handle:
            assert handle.read() == b"streamed-payload"
        return WfxResponse(ok=True, data={"ok": True})

    monkeypatch.setattr(bridge_routes, "upload_path", fake_upload_path)

    response = client.post(
        "/bridge/wfx/upload-raw",
        data={
            "destination": "alfresco:/contracts",
            "file_name": "upload.bin",
            "overwrite": "true",
            "auth_json": json.dumps(_auth()),
        },
        files={"file": ("upload.bin", b"streamed-payload", "application/octet-stream")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True


def test_upload_stream_alias_streams_file_via_source_path(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(create_app())

    def fake_upload_path(destination, file_name, auth, content_base64=None, source_path=None, overwrite=False):
        assert destination == "alfresco:/contracts"
        assert file_name == "upload.bin"
        assert content_base64 is None
        assert isinstance(source_path, str)
        with open(source_path, "rb") as handle:
            assert handle.read() == b"streamed-payload"
        return WfxResponse(ok=True, data={"ok": True})

    monkeypatch.setattr(bridge_routes, "upload_path", fake_upload_path)

    response = client.post(
        "/bridge/wfx/upload-stream",
        data={
            "destination": "alfresco:/contracts",
            "file_name": "upload.bin",
            "overwrite": "true",
            "auth_json": json.dumps(_auth()),
        },
        files={"file": ("upload.bin", b"streamed-payload", "application/octet-stream")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True


def test_upload_raw_rejects_payload_over_configured_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(create_app())

    monkeypatch.setattr(bridge_routes, "load_config", lambda: {"upload": {"raw": {"maxBytes": 4}}})

    response = client.post(
        "/bridge/wfx/upload-raw",
        data={
            "destination": "alfresco:/contracts",
            "file_name": "too-large.bin",
            "overwrite": "false",
            "auth_json": json.dumps(_auth()),
        },
        files={"file": ("too-large.bin", b"12345", "application/octet-stream")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "exceeds configured raw limit" in body["message"]


def test_download_returns_json_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(create_app())

    monkeypatch.setattr(
        bridge_routes,
        "download_path",
        lambda path, auth: WfxResponse(
            ok=True,
            data={
                "content_base64": "SGVsbG8=",
                "mime_type": "text/plain",
                "source": "/contracts/sample.txt",
            },
            metadata={"provider": "alfresco", "operation": "download"},
        ),
    )

    response = client.post(
        "/bridge/wfx/download",
        json={"path": "alfresco:/contracts/sample.txt", "auth": _auth()},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["data"]["content_base64"] == "SGVsbG8="


def test_download_raw_returns_binary_attachment(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(create_app())

    monkeypatch.setattr(bridge_routes, "open_download_stream", lambda path, auth: None)
    monkeypatch.setattr(
        bridge_routes,
        "download_path",
        lambda path, auth: WfxResponse(
            ok=True,
            data={
                "content_base64": "SGVsbG8=",
                "mime_type": "text/plain",
                "source": "/contracts/sample.txt",
            },
            metadata={"provider": "alfresco", "operation": "download"},
        ),
    )

    response = client.post(
        "/bridge/wfx/download-raw",
        json={"path": "alfresco:/contracts/sample.txt", "auth": _auth()},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/plain; charset=utf-8"
    assert response.headers["content-disposition"] == 'attachment; filename="sample.txt"; filename*=UTF-8\'\'sample.txt'
    assert response.content == b"Hello"


def test_download_raw_streams_when_provider_supports_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(create_app())

    def fake_open_download_stream(path, auth):
        assert path == "alfresco:/contracts/sample.txt"
        return WfxResponse(
            ok=True,
            data={
                "stream": io.BytesIO(b"streamed-payload"),
                "mime_type": "application/octet-stream",
                "source": "/contracts/sample.txt",
                "size": 16,
            },
            metadata={"provider": "alfresco", "operation": "download"},
        )

    monkeypatch.setattr(bridge_routes, "open_download_stream", fake_open_download_stream)

    response = client.post(
        "/bridge/wfx/download-raw",
        json={"path": "alfresco:/contracts/sample.txt", "auth": _auth()},
    )

    assert response.status_code == 200
    assert response.headers["x-bridge-raw-content"] == "1"
    assert response.headers["content-length"] == "16"
    assert response.content == b"streamed-payload"


def test_download_raw_uses_rfc5987_for_unicode_filename(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(create_app())

    monkeypatch.setattr(bridge_routes, "open_download_stream", lambda path, auth: None)
    monkeypatch.setattr(
        bridge_routes,
        "download_path",
        lambda path, auth: WfxResponse(
            ok=True,
            data={
                "content_base64": "SGVsbG8=",
                "mime_type": "text/plain",
                "source": "/contracts/Příliš žluťoučký.txt",
            },
            metadata={"provider": "alfresco", "operation": "download"},
        ),
    )

    response = client.post(
        "/bridge/wfx/download-raw",
        json={"path": "alfresco:/contracts/unicode.txt", "auth": _auth()},
    )

    assert response.status_code == 200
    header = response.headers["content-disposition"]
    assert header.startswith("attachment; filename=")
    assert "filename*=UTF-8''P%C5%99%C3%ADli%C5%A1%20%C5%BElu%C5%A5ou%C4%8Dk%C3%BD.txt" in header

