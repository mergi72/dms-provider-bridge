from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from edocat_bridge.app.server import create_app
from edocat_bridge.app.routes import bridge as bridge_routes
from edocat_bridge.models.bridge import WfxResponse


pytestmark = pytest.mark.integration


def _auth() -> dict[str, str]:
    return {"mode": "winuser", "win_user": "DOMAIN\\tester"}


def _share_url() -> str:
    return (
        "https://cheminvest.edocat.net/share/page/site/deals/documentlibrary"
        "#/03%20zak%C3%A1zky%20v%20realizaci/22%20080%20-%20UNI_Novy%20odolejovac%20bl.%2068"
        "/05%20Realizace/04%20Dokumentace/13%20-%20CHI/Test_DMS/Upload?page=1"
    )


def _source_file_path() -> str:
    return (
        "/03 zakazky v realizaci/22 080 - UNI_Novy odolejovac bl. 68"
        "/05 Realizace/04 Dokumentace/13 - CHI/Test_DMS/Upload/sample.txt"
    )


def _target_file_path(name: str) -> str:
    return (
        "/03 zakazky v realizaci/22 080 - UNI_Novy odolejovac bl. 68"
        f"/05 Realizace/04 Dokumentace/13 - CHI/Test_DMS/Upload/{name}"
    )


def _target_folder_path(name: str) -> str:
    return (
        "/03 zakazky v realizaci/22 080 - UNI_Novy odolejovac bl. 68"
        f"/05 Realizace/04 Dokumentace/13 - CHI/Test_DMS/Upload/{name}"
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
    assert set(body["data"]["providers"]) >= {"edocat", "alfresco", "fso"}
    assert body["data"]["default_provider"] in body["data"]["providers"]


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


def test_download_raw_uses_rfc5987_for_unicode_filename(monkeypatch: pytest.MonkeyPatch) -> None:
    client = TestClient(create_app())

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
