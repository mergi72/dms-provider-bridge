from __future__ import annotations

from typing import Any
from urllib.error import HTTPError

import pytest

import dms_provider_bridge.providers.webdav as webdav_provider_module
from dms_provider_bridge.models.bridge import BridgeAuthContext
from dms_provider_bridge.providers.webdav import WebdavProvider


pytestmark = pytest.mark.unit


class FakeResponse:
    status = 207
    headers: dict[str, str] = {}

    def __init__(self, content: bytes) -> None:
        self._content = content

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    def read(self) -> bytes:
        return self._content


def test_webdav_list_maps_propfind_children(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    xml = b"""<?xml version="1.0" encoding="utf-8"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/remote.php/dav/files/katherine/</d:href>
    <d:propstat><d:prop><d:displayname>katherine</d:displayname><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat>
  </d:response>
  <d:response>
    <d:href>/remote.php/dav/files/katherine/Documents/</d:href>
    <d:propstat><d:prop><d:displayname>Documents</d:displayname><d:resourcetype><d:collection/></d:resourcetype><d:getlastmodified>Sat, 20 Jun 2026 07:00:00 GMT</d:getlastmodified></d:prop></d:propstat>
  </d:response>
  <d:response>
    <d:href>/remote.php/dav/files/katherine/readme.txt</d:href>
    <d:propstat><d:prop><d:displayname>readme.txt</d:displayname><d:resourcetype/><d:getcontentlength>42</d:getcontentlength><d:getcontenttype>text/plain</d:getcontenttype><d:getetag>"etag-1"</d:getetag></d:prop></d:propstat>
  </d:response>
</d:multistatus>
"""

    def fake_urlopen(req: object, timeout: int) -> FakeResponse:
        captured["method"] = getattr(req, "method")
        captured["url"] = getattr(req, "full_url")
        captured["headers"] = dict(getattr(req, "headers"))
        captured["timeout"] = timeout
        return FakeResponse(xml)

    monkeypatch.setattr(webdav_provider_module.request, "urlopen", fake_urlopen)
    provider = WebdavProvider(
        name="webdav1",
        config={
            "base_url": "https://demo.owncloud.com/remote.php/dav/files/katherine",
            "root_path": "/",
            "limits": {"timeouts": {"requestSeconds": 12}},
        },
    )

    result = provider.list_items("/", BridgeAuthContext(mode="credentials", username="katherine", password="gemini"))

    assert result.provider == "webdav1"
    assert result.total == 2
    assert [item.name for item in result.items] == ["Documents", "readme.txt"]
    assert result.items[0].is_folder is True
    assert result.items[1].size == 42
    assert result.items[1].mime_type == "text/plain"
    assert captured["method"] == "PROPFIND"
    assert captured["url"] == "https://demo.owncloud.com/remote.php/dav/files/katherine/"
    assert captured["headers"]["Depth"] == "1"
    assert "Authorization" in captured["headers"]
    assert captured["timeout"] == 12


def test_webdav_bearer_scheme_uses_password_as_token(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    xml = b"""<?xml version="1.0" encoding="utf-8"?>
<d:multistatus xmlns:d="DAV:">
  <d:response>
    <d:href>/remote.php/dav/files/katherine/</d:href>
    <d:propstat><d:prop><d:displayname>katherine</d:displayname><d:resourcetype><d:collection/></d:resourcetype></d:prop></d:propstat>
  </d:response>
</d:multistatus>
"""

    def fake_urlopen(req: object, timeout: int) -> FakeResponse:
        _ = timeout
        captured["headers"] = dict(getattr(req, "headers"))
        return FakeResponse(xml)

    monkeypatch.setattr(webdav_provider_module.request, "urlopen", fake_urlopen)
    provider = WebdavProvider(
        name="webdav1",
        config={
            "base_url": "https://demo.owncloud.com/remote.php/dav/files/katherine",
            "credentials": {"authScheme": "bearer"},
        },
    )

    provider.list_items("/", BridgeAuthContext(mode="credentials", username="katherine", password="access-token"))

    assert provider.upstream_auth_scheme == "bearer"
    assert captured["headers"]["Authorization"] == "Bearer access-token"


def test_webdav_upload_uses_put(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req: object, timeout: int) -> FakeResponse:
        _ = timeout
        captured["method"] = getattr(req, "method")
        captured["url"] = getattr(req, "full_url")
        captured["headers"] = dict(getattr(req, "headers"))
        captured["body"] = getattr(req, "data")
        return FakeResponse(b"")

    monkeypatch.setattr(webdav_provider_module.request, "urlopen", fake_urlopen)
    provider = WebdavProvider(name="webdav1", config={"base_url": "http://127.0.0.1:8080"})

    result = provider.upload_item(
        "/",
        "hello.txt",
        content_base64="aGVsbG8=",
        auth=BridgeAuthContext(mode="credentials", username="meri", password="test"),
    )

    assert result.success is True
    assert result.destination == "/hello.txt"
    assert captured["method"] == "PUT"
    assert captured["url"] == "http://127.0.0.1:8080/hello.txt"
    assert captured["body"] == b"hello"
    assert captured["headers"]["Content-type"] == "text/plain"
    assert captured["headers"]["Overwrite"] == "F"


def test_webdav_download_uses_get_and_returns_base64(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req: object, timeout: int) -> FakeResponse:
        _ = timeout
        captured["method"] = getattr(req, "method")
        captured["url"] = getattr(req, "full_url")
        response = FakeResponse(b"hello")
        response.headers = {"Content-Type": "text/plain"}
        return response

    monkeypatch.setattr(webdav_provider_module.request, "urlopen", fake_urlopen)
    provider = WebdavProvider(name="webdav1", config={"base_url": "http://127.0.0.1:8080"})

    result = provider.download_item("/hello.txt", BridgeAuthContext(mode="credentials", username="meri", password="test"))

    assert result.success is True
    assert result.content_base64 == "aGVsbG8="
    assert result.size == 5
    assert result.mime_type == "text/plain"
    assert captured["method"] == "GET"
    assert captured["url"] == "http://127.0.0.1:8080/hello.txt"


def test_webdav_make_dir_and_delete_use_webdav_methods(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[tuple[str, str]] = []

    def fake_urlopen(req: object, timeout: int) -> FakeResponse:
        _ = timeout
        captured.append((getattr(req, "method"), getattr(req, "full_url")))
        return FakeResponse(b"")

    monkeypatch.setattr(webdav_provider_module.request, "urlopen", fake_urlopen)
    provider = WebdavProvider(name="webdav1", config={"base_url": "http://127.0.0.1:8080"})
    auth = BridgeAuthContext(mode="credentials", username="meri", password="test")

    mkdir = provider.make_dir("/folder", auth)
    delete = provider.delete_item("/folder", auth)

    assert mkdir.success is True
    assert delete.success is True
    assert captured == [
        ("MKCOL", "http://127.0.0.1:8080/folder/"),
        ("DELETE", "http://127.0.0.1:8080/folder"),
    ]


def test_webdav_stat_missing_file_returns_none_without_directory_slash(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req: object, timeout: int) -> FakeResponse:
        _ = timeout
        captured["method"] = getattr(req, "method")
        captured["url"] = getattr(req, "full_url")
        raise HTTPError(captured["url"], 404, "Not Found", {}, None)

    monkeypatch.setattr(webdav_provider_module.request, "urlopen", fake_urlopen)
    provider = WebdavProvider(name="webdav1", config={"base_url": "http://127.0.0.1:8080"})

    result = provider.stat_item("/rename_.pdf", BridgeAuthContext(mode="credentials", username="meri", password="test"))

    assert result is None
    assert captured["method"] == "PROPFIND"
    assert captured["url"] == "http://127.0.0.1:8080/rename_.pdf"
