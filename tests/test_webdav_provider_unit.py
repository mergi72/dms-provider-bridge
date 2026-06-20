from __future__ import annotations

from typing import Any

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
