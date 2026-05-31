from __future__ import annotations

# pyright: reportMissingTypeStubs=false

import json
from typing import Any
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock

import pytest

import edocat_bridge.clients.edocat_client as edocat_client_module  # type: ignore[import-untyped]
import edocat_bridge.providers.edocat as edocat_provider_module  # type: ignore[import-untyped]
from edocat_bridge.clients.edocat_client import EdocatClient  # type: ignore[import-untyped]
from edocat_bridge.models.bridge import BridgeAuthContext  # type: ignore[import-untyped]
from edocat_bridge.providers.edocat import EdocatProvider  # type: ignore[import-untyped]


pytestmark = pytest.mark.unit


class FakeResponse:
    def __init__(self, body: str = "{}") -> None:
        self._body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._body.encode("utf-8")


class FakeClient:
    def __init__(self) -> None:
        self.query_nodes = Mock()
        self.create_node = Mock(return_value={"uuid": "created-uuid"})
        self.update_node = Mock(return_value={"uuid": "updated-uuid"})
        self.delete_nodes = Mock(return_value={"ok": True})

    def endpoint_url(self, endpoint_key: str) -> str:
        return {
            "query": "https://example.test/api/v1/node/query",
            "node": "https://example.test/api/v1/node",
        }[endpoint_key]


def _make_provider(monkeypatch: pytest.MonkeyPatch, client: FakeClient | None = None) -> EdocatProvider:
    monkeypatch.setattr(edocat_provider_module, "load_provider_config", lambda name: {"doc_library": "/deals"})
    monkeypatch.setattr(edocat_provider_module.EdocatClient, "from_config", lambda config: client or FakeClient())
    return EdocatProvider()


def test_client_create_update_and_delete_payloads(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(req, timeout=30):
        captured["method"] = req.get_method()
        captured["url"] = req.full_url
        captured["data"] = req.data
        captured["headers"] = dict(req.headers)
        return FakeResponse('{"ok": true}')

    monkeypatch.setattr(edocat_client_module.request, "urlopen", fake_urlopen)

    client = EdocatClient(
        base_url="https://example.test",
        api_root="edocat/api/v1",
        endpoints={"node": "node", "query": "node/query"},
        doc_library="/deals",
    )

    create_result = client.create_node({"name": "sample.txt"}, username="user", password="pass")
    assert create_result == {"ok": True}
    assert captured["method"] == "POST"
    assert captured["url"] == "https://example.test/edocat/api/v1/node"
    assert isinstance(captured["data"], bytes)
    assert json.loads(captured["data"].decode("utf-8")) == {"name": "sample.txt"}
    assert isinstance(captured["headers"], dict)
    assert captured["headers"]["Content-type"] == "application/json"
    assert captured["headers"]["Authorization"].startswith("Basic ")

    captured.clear()
    update_result = client.update_node({"uuid": "123", "name": "renamed.txt"}, username="user", password="pass")
    assert update_result == {"ok": True}
    assert captured["method"] == "PUT"
    assert isinstance(captured["data"], bytes)
    assert json.loads(captured["data"].decode("utf-8")) == {"uuid": "123", "name": "renamed.txt"}

    captured.clear()
    delete_result = client.delete_nodes(["a", "b"], username="user", password="pass")
    assert delete_result == {"ok": True}
    assert captured["method"] == "DELETE"
    query = parse_qs(urlparse(str(captured["url"])).query)
    assert query["uuids"] == ["a", "b"]


def test_rename_item_uses_update_node(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.query_nodes.return_value = {
        "nodes": [{"uuid": "node-1", "name": "old.txt", "path": "/deals/folder/old.txt", "nodeType": "ctbd:baseDoc"}]
    }
    provider = _make_provider(monkeypatch, client)

    result = provider.rename_item("/folder/old.txt", "/folder/new.txt", BridgeAuthContext(mode="credentials", username="user", password="pass"))

    assert result.success is True
    assert result.operation == "rename"
    assert result.destination == "/deals/folder/new.txt"
    client.update_node.assert_called_once_with(
        {"uuid": "node-1", "path": "deals/folder", "name": "new.txt"},
        username="user",
        password="pass",
    )


def test_delete_item_uses_delete_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.query_nodes.return_value = {
        "nodes": [{"uuid": "node-2", "name": "to-delete.txt", "path": "/deals/folder/to-delete.txt", "nodeType": "ctbd:baseDoc"}]
    }
    provider = _make_provider(monkeypatch, client)

    result = provider.delete_item("/folder/to-delete.txt", BridgeAuthContext(mode="credentials", username="user", password="pass"))

    assert result.success is True
    assert result.operation == "delete"
    client.delete_nodes.assert_called_once_with(["node-2"], username="user", password="pass")


def test_make_dir_sends_folder_node_type(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _make_provider(monkeypatch, client)

    result = provider.make_dir("/folder/new-folder", BridgeAuthContext(mode="credentials", username="user", password="pass"))

    assert result.success is True
    assert result.operation == "mkdir"
    client.create_node.assert_called_once_with(
        {"path": "deals/folder", "name": "new-folder", "nodeType": "ctfd:baseFolder"},
        username="user",
        password="pass",
    )


def test_upload_item_sends_inline_content_and_overwrite_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _make_provider(monkeypatch, client)

    result = provider.upload_item(
        "/folder",
        "upload.txt",
        content_base64="dGVzdA==",
        overwrite=True,
        auth=BridgeAuthContext(mode="credentials", username="user", password="pass"),
    )

    assert result.success is True
    assert result.operation == "upload"
    client.create_node.assert_called_once_with(
        {"path": "deals/folder", "name": "upload.txt", "content": "dGVzdA==", "nodeType": "ctbd:baseDoc", "autoRename": False},
        username="user",
        password="pass",
    )


def test_copy_item_clones_content_and_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.query_nodes.return_value = {
        "nodes": [
            {
                "uuid": "source-1",
                "name": "source.txt",
                "path": "/deals/folder/source.txt",
                "nodeType": "ctbd:baseDoc",
                "content": "c291cmNl",
                "mimeType": "text/plain",
                "props": {"title": "Source"},
                "tags": ["tag-a"],
                "attachment": [{"name": "attachment.txt"}],
                "relatedDocs": ["related-1"],
            }
        ]
    }
    provider = _make_provider(monkeypatch, client)

    result = provider.copy_item("/folder/source.txt", "/folder/copied.txt", BridgeAuthContext(mode="credentials", username="user", password="pass"))

    assert result.success is True
    assert result.operation == "copy"
    client.create_node.assert_called_once_with(
        {
            "path": "deals/folder",
            "name": "copied.txt",
            "nodeType": "ctbd:baseDoc",
            "props": {"title": "Source"},
            "tags": ["tag-a"],
            "content": "c291cmNl",
            "mimeType": "text/plain",
            "attachment": [{"name": "attachment.txt"}],
            "relatedDocs": ["related-1"],
        },
        username="user",
        password="pass",
    )


def test_download_item_reports_decoded_binary_size(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.query_nodes.return_value = {
        "nodes": [
            {
                "uuid": "node-1",
                "name": "sample.txt",
                "path": "/deals/folder/sample.txt",
                "nodeType": "ctbd:baseDoc",
                "content": "dGVzdA==",
                "mimeType": "text/plain",
            }
        ]
    }
    provider = _make_provider(monkeypatch, client)

    result = provider.download_item("/folder/sample.txt", BridgeAuthContext(mode="credentials", username="user", password="pass"))

    assert result.success is True
    assert result.content_base64 == "dGVzdA=="
    assert result.size == 4


def test_stat_item_prefers_exact_path_over_first_query_result(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.query_nodes.return_value = {
        "nodes": [
            {"uuid": "welcome-1", "name": "welcome.pdf", "path": "/deals/folder/welcome.pdf", "nodeType": "ctbd:baseDoc"},
            {"uuid": "target-1", "name": "target.pdf", "path": "/deals/folder/target.pdf", "nodeType": "ctbd:baseDoc"},
        ]
    }
    provider = _make_provider(monkeypatch, client)

    item = provider.stat_item("/folder/target.pdf", BridgeAuthContext(mode="credentials", username="user", password="pass"))

    assert item is not None
    assert item.id == "target-1"
    assert item.name == "target.pdf"
    assert item.path == "/deals/folder/target.pdf"


def test_stat_item_missing_leaf_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.query_nodes.return_value = {"nodes": []}
    provider = _make_provider(monkeypatch, client)

    item = provider.stat_item("/folder/missing.pdf", BridgeAuthContext(mode="credentials", username="user", password="pass"))

    assert item is None