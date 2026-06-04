from __future__ import annotations

# pyright: reportMissingTypeStubs=false

import base64
import json
from typing import Any
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from unittest.mock import Mock

import pytest

import edocat_bridge.clients.edocat_client as edocat_client_module  # type: ignore[import-untyped]
import edocat_bridge.providers.edocat as edocat_provider_module  # type: ignore[import-untyped]
from edocat_bridge.clients.edocat_client import EdocatClient  # type: ignore[import-untyped]
from edocat_bridge.core.errors import AuthenticationError, ProviderOperationError  # type: ignore[import-untyped]
from edocat_bridge.models.bridge import BridgeAuthContext  # type: ignore[import-untyped]
from edocat_bridge.models.operation import OperationResult  # type: ignore[import-untyped]
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
        self.request_bytes = Mock(return_value=(b"PK\x03\x04", "application/zip"))

    def endpoint_url(self, endpoint_key: str) -> str:
        return {
            "query": "https://example.test/api/v1/node/query",
            "node": "https://example.test/api/v1/node",
        }[endpoint_key]


def _make_provider(
    monkeypatch: pytest.MonkeyPatch,
    client: FakeClient | None = None,
    config: dict[str, Any] | None = None,
) -> EdocatProvider:
    provider_config = config or {"doc_library": "/deals"}
    monkeypatch.setattr(edocat_provider_module, "load_provider_config", lambda name: provider_config)
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
    assert result.destination == "/folder/new.txt"
    client.update_node.assert_called_once_with(
        {"uuid": "node-1", "name": "new.txt"},
        username="user",
        password="pass",
    )
    client.delete_nodes.assert_not_called()


def test_rename_item_move_across_parent_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.query_nodes.return_value = {
        "nodes": [{"uuid": "node-1", "name": "old.txt", "path": "/deals/folder/old.txt", "nodeType": "ctbd:baseDoc"}]
    }
    provider = _make_provider(monkeypatch, client)

    with pytest.raises(Exception, match="supports only name/metadata changes"):
        provider.rename_item(
            "/folder/old.txt",
            "/other/new.txt",
            BridgeAuthContext(mode="credentials", username="user", password="pass"),
        )

    client.update_node.assert_not_called()


def test_rename_item_does_not_perform_delete_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.query_nodes.return_value = {
        "nodes": [{"uuid": "node-1", "name": "old-folder", "path": "/deals/folder/old-folder", "nodeType": "ctfd:baseFolder"}]
    }
    provider = _make_provider(monkeypatch, client)

    result = provider.rename_item(
        "/folder/old-folder",
        "/folder/new-folder",
        BridgeAuthContext(mode="credentials", username="user", password="pass"),
    )

    assert result.success is True
    client.update_node.assert_called_once_with(
        {"uuid": "node-1", "name": "new-folder"},
        username="user",
        password="pass",
    )
    client.delete_nodes.assert_not_called()


def test_rename_item_rejects_path_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _make_provider(monkeypatch, client)
    monkeypatch.setattr(
        provider,
        "_query_single_node",
        lambda path, auth, include_content=False: {"uuid": "child-1", "name": "test.json", "path": "/deals/folder/Upload/test.json", "nodeType": "ctbd:baseDoc"},
    )

    with pytest.raises(Exception, match="source path mismatch"):
        provider.rename_item(
            "/folder/Upload",
            "/folder/Upload_101",
            BridgeAuthContext(mode="credentials", username="user", password="pass"),
        )

    client.update_node.assert_not_called()


def test_rename_item_uses_folder_node_when_edocat_path_is_parent_only(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.query_nodes.return_value = {
        "nodes": [
            {
                "uuid": "folder-1",
                "name": "projekt",
                "path": "/deals/03 zakázky v realizaci/22 080 - UNI_Novy odolejovac bl. 68/05 Realizace/04 Dokumentace/13 - CHI/Test_DMS",
                "nodeType": "ctfd:baseFolder",
            },
            {
                "uuid": "file-1",
                "name": "soubor.txt",
                "path": "/deals/03 zakázky v realizaci/22 080 - UNI_Novy odolejovac bl. 68/05 Realizace/04 Dokumentace/13 - CHI/Test_DMS/projekt",
                "nodeType": "ctbd:baseDoc",
            },
        ]
    }
    provider = _make_provider(monkeypatch, client)

    result = provider.rename_item(
        "/03 zakázky v realizaci/22 080 - UNI_Novy odolejovac bl. 68/05 Realizace/04 Dokumentace/13 - CHI/Test_DMS/projekt",
        "/03 zakázky v realizaci/22 080 - UNI_Novy odolejovac bl. 68/05 Realizace/04 Dokumentace/13 - CHI/Test_DMS/bambule",
        BridgeAuthContext(mode="credentials", username="user", password="pass"),
    )

    assert result.success is True
    client.update_node.assert_called_once_with(
        {"uuid": "folder-1", "name": "bambule"},
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


def test_delete_item_rejects_path_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _make_provider(monkeypatch, client)
    monkeypatch.setattr(
        provider,
        "_query_single_node",
        lambda path, auth, include_content=False: {
            "uuid": "child-1",
            "name": "test.json",
            "path": "/deals/folder/Upload/test.json",
            "nodeType": "ctbd:baseDoc",
        },
    )

    with pytest.raises(Exception, match="target path mismatch"):
        provider.delete_item(
            "/folder/Upload",
            BridgeAuthContext(mode="credentials", username="user", password="pass"),
        )

    client.delete_nodes.assert_not_called()


def test_delete_item_rejects_folder_tree_above_safety_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _make_provider(
        monkeypatch,
        client,
        config={
            "doc_library": "/deals",
            "delete": {"maxNodes": 2},
            "nodeType": {
                "baseFolder": "com.onlio.edocat.BaseFolder",
            },
        },
    )

    source_root = {
        "uuid": "folder-1",
        "name": "abcd",
        "path": "/deals/folder/abcd",
        "nodeType": "com.onlio.edocat.BaseFolder",
    }
    source_child_a = {
        "uuid": "folder-2",
        "name": "nested-a",
        "path": "/deals/folder/abcd/nested-a",
        "nodeType": "com.onlio.edocat.BaseFolder",
    }
    source_child_b = {
        "uuid": "folder-3",
        "name": "nested-b",
        "path": "/deals/folder/abcd/nested-b",
        "nodeType": "com.onlio.edocat.BaseFolder",
    }

    monkeypatch.setattr(
        provider,
        "_query_single_node",
        lambda path, auth, include_content=False: {"/deals/folder/abcd": source_root}.get(path),
    )
    monkeypatch.setattr(
        provider,
        "_direct_child_nodes",
        lambda folder_path, auth, include_content=False: {
            "/deals/folder/abcd": [source_child_a, source_child_b],
            "/deals/folder/abcd/nested-a": [],
            "/deals/folder/abcd/nested-b": [],
        }.get(provider._resolve_path(folder_path), []),
    )

    with pytest.raises(Exception, match="folder tree has"):
        provider.delete_item(
            "/folder/abcd",
            BridgeAuthContext(mode="credentials", username="user", password="pass"),
        )

    client.delete_nodes.assert_not_called()


def test_list_items_returns_only_direct_children(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.query_nodes.return_value = {
        "nodes": [
            {
                "uuid": "parent",
                "name": "folder",
                "path": "/deals/folder",
                "nodeType": "com.onlio.edocat.BaseFolder",
            },
            {
                "uuid": "direct-folder",
                "name": "sub",
                "path": "/deals/folder",
                "nodeType": "com.onlio.edocat.BaseFolder",
            },
            {
                "uuid": "direct-file",
                "name": "a.txt",
                "path": "/deals/folder",
                "nodeType": "com.onlio.edocat.BaseDoc",
            },
            {
                "uuid": "nested-file",
                "name": "deep.txt",
                "path": "/deals/folder/sub",
                "nodeType": "com.onlio.edocat.BaseDoc",
            },
        ]
    }
    provider = _make_provider(monkeypatch, client)

    listing = provider.list_items("/folder", BridgeAuthContext(mode="credentials", username="user", password="pass"))

    assert listing.path == "/folder"
    assert listing.total == 2
    assert [item.name for item in listing.items] == ["sub", "a.txt"]


def test_delete_item_deletes_folder_bottom_up(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _make_provider(
        monkeypatch,
        client,
        config={
            "doc_library": "/deals",
            "delete": {"maxNodes": 10},
        },
    )

    root = {
        "uuid": "folder-1",
        "name": "abcd",
        "path": "/deals/folder/abcd",
        "nodeType": "com.onlio.edocat.BaseFolder",
    }
    nested = {
        "uuid": "folder-2",
        "name": "nested",
        "path": "/deals/folder/abcd/nested",
        "nodeType": "com.onlio.edocat.BaseFolder",
    }
    nested_file = {
        "uuid": "file-1",
        "name": "inside.txt",
        "path": "/deals/folder/abcd/nested/inside.txt",
        "nodeType": "ctbd:baseDoc",
    }

    monkeypatch.setattr(provider, "_count_folder_tree_nodes", lambda folder_path, auth: 3)
    monkeypatch.setattr(
        provider,
        "_query_nodes",
        lambda path, auth, include_content=False: {
            "/deals/folder/abcd": [nested],
            "/deals/folder/abcd/nested": [nested_file],
        }.get(provider._resolve_path(path), []),
    )
    monkeypatch.setattr(
        provider,
        "_query_single_node",
        lambda path, auth, include_content=False: {
            "/deals/folder/abcd": root,
            "/deals/folder/abcd/nested": nested,
            "/deals/folder/abcd/nested/inside.txt": nested_file,
        }.get(provider._resolve_path(path)),
    )

    result = provider.delete_item(
        "/folder/abcd",
        BridgeAuthContext(mode="credentials", username="user", password="pass"),
    )

    assert result.success is True
    assert [call.args[0] for call in client.delete_nodes.call_args_list] == [["file-1"], ["folder-2"], ["folder-1"]]


def test_make_dir_sends_folder_node_type(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _make_provider(monkeypatch, client)

    result = provider.make_dir("/folder/new-folder", BridgeAuthContext(mode="credentials", username="user", password="pass"))

    assert result.success is True
    assert result.operation == "mkdir"
    client.create_node.assert_called_once_with(
        {"path": "deals/folder", "name": "new-folder", "nodeType": "com.onlio.edocat.BaseFolder"},
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


def test_upload_item_prefers_base_doc_node_type_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _make_provider(
        monkeypatch,
        client,
        config={
            "doc_library": "/deals",
            "nodeType": {
                "file": "com.onlio.edocat.File",
                "baseDoc": "com.onlio.edocat.BaseDoc",
            },
        },
    )

    result = provider.upload_item(
        "/folder",
        "upload.txt",
        content_base64="dGVzdA==",
        overwrite=False,
        auth=BridgeAuthContext(mode="credentials", username="user", password="pass"),
    )

    assert result.success is True
    assert result.operation == "upload"
    client.create_node.assert_called_once_with(
        {"path": "deals/folder", "name": "upload.txt", "content": "dGVzdA==", "nodeType": "com.onlio.edocat.BaseDoc"},
        username="user",
        password="pass",
    )


def test_upload_item_rejects_source_path_raw_mode(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    client = FakeClient()
    provider = _make_provider(monkeypatch, client)
    source = tmp_path / "upload.txt"
    source.write_bytes(b"hello")

    with pytest.raises(ProviderOperationError, match="raw stream mode is not supported"):
        provider.upload_item(
            "/folder",
            "upload.txt",
            source_path=str(source),
            overwrite=False,
            auth=BridgeAuthContext(mode="credentials", username="user", password="pass"),
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
            "content": "c291cmNl",
            "mimeType": "text/plain",
        },
        username="user",
        password="pass",
    )


def test_copy_item_rejects_path_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _make_provider(monkeypatch, client)
    monkeypatch.setattr(
        provider,
        "_query_single_node",
        lambda path, auth, include_content=False: {
            "uuid": "child-1",
            "name": "test.json",
            "path": "/deals/folder/Upload/test.json",
            "nodeType": "ctbd:baseDoc",
        },
    )

    with pytest.raises(Exception, match="source path mismatch"):
        provider.copy_item(
            "/folder/Upload",
            "/folder/Upload_copy",
            BridgeAuthContext(mode="credentials", username="user", password="pass"),
        )

    client.create_node.assert_not_called()


def test_copy_item_uses_folder_node_type_for_folders(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.query_nodes.return_value = {
        "nodes": [
            {
                "uuid": "folder-1",
                "name": "abcd",
                "path": "/deals/folder/abcd",
                "nodeType": "com.onlio.edocat.BaseFolder",
            }
        ]
    }
    provider = _make_provider(
        monkeypatch,
        client,
        config={
            "doc_library": "/deals",
            "nodeType": {
                "baseFolder": "com.onlio.edocat.BaseFolder",
                "baseDoc": "com.onlio.edocat.BaseDoc",
            },
        },
    )

    result = provider.copy_item(
        "/folder/abcd",
        "/folder/abcd_copy",
        BridgeAuthContext(mode="credentials", username="user", password="pass"),
    )

    assert result.success is True
    client.create_node.assert_called_once_with(
        {
            "path": "deals/folder",
            "name": "abcd_copy",
            "nodeType": "com.onlio.edocat.BaseFolder",
        },
        username="user",
        password="pass",
    )


def test_copy_item_recursively_copies_folder_children(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _make_provider(
        monkeypatch,
        client,
        config={
            "doc_library": "/deals",
            "nodeType": {
                "baseFolder": "com.onlio.edocat.BaseFolder",
                "baseDoc": "com.onlio.edocat.BaseDoc",
            },
        },
    )

    source_root = {
        "uuid": "folder-1",
        "name": "abcd",
        "path": "/deals/folder/abcd",
        "nodeType": "com.onlio.edocat.BaseFolder",
    }
    source_nested_folder = {
        "uuid": "folder-2",
        "name": "nested",
        "path": "/deals/folder/abcd/nested",
        "nodeType": "com.onlio.edocat.BaseFolder",
    }
    source_file = {
        "uuid": "file-1",
        "name": "inside.txt",
        "path": "/deals/folder/abcd/nested/inside.txt",
        "nodeType": "com.onlio.edocat.BaseDoc",
        "content": "aGVsbG8=",
        "mimeType": "text/plain",
    }

    monkeypatch.setattr(
        provider,
        "_query_single_node",
        lambda path, auth, include_content=False: {
            "/deals/folder/abcd": source_root,
            "/deals/folder/abcd/nested/inside.txt": source_file,
        }.get(path),
    )
    monkeypatch.setattr(
        provider,
        "_direct_child_nodes",
        lambda folder_path, auth, include_content=False: {
            "/deals/folder/abcd": [source_nested_folder],
            "/deals/folder/abcd/nested": [source_file],
        }.get(provider._resolve_path(folder_path), []),
    )

    result = provider.copy_item(
        "/folder/abcd",
        "/folder/abcd_copy",
        BridgeAuthContext(mode="credentials", username="user", password="pass"),
    )

    assert result.success is True
    assert client.create_node.call_count == 3
    assert client.create_node.call_args_list[0].args[0] == {
        "path": "deals/folder",
        "name": "abcd_copy",
        "nodeType": "com.onlio.edocat.BaseFolder",
    }
    assert client.create_node.call_args_list[1].args[0] == {
        "path": "deals/folder/abcd_copy",
        "name": "nested",
        "nodeType": "com.onlio.edocat.BaseFolder",
    }
    assert client.create_node.call_args_list[2].args[0] == {
        "path": "deals/folder/abcd_copy/nested",
        "name": "inside.txt",
        "nodeType": "com.onlio.edocat.BaseDoc",
        "content": "aGVsbG8=",
        "mimeType": "text/plain",
    }


def test_copy_item_rejects_folder_tree_above_safety_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _make_provider(
        monkeypatch,
        client,
        config={
            "doc_library": "/deals",
            "copy": {"maxNodes": 2},
            "nodeType": {
                "baseFolder": "com.onlio.edocat.BaseFolder",
                "baseDoc": "com.onlio.edocat.BaseDoc",
            },
        },
    )

    source_root = {
        "uuid": "folder-1",
        "name": "abcd",
        "path": "/deals/folder/abcd",
        "nodeType": "com.onlio.edocat.BaseFolder",
    }
    source_child_a = {
        "uuid": "folder-2",
        "name": "nested-a",
        "path": "/deals/folder/abcd/nested-a",
        "nodeType": "com.onlio.edocat.BaseFolder",
    }
    source_child_b = {
        "uuid": "folder-3",
        "name": "nested-b",
        "path": "/deals/folder/abcd/nested-b",
        "nodeType": "com.onlio.edocat.BaseFolder",
    }

    monkeypatch.setattr(
        provider,
        "_query_single_node",
        lambda path, auth, include_content=False: {"/deals/folder/abcd": source_root}.get(path),
    )
    monkeypatch.setattr(
        provider,
        "_direct_child_nodes",
        lambda folder_path, auth, include_content=False: {
            "/deals/folder/abcd": [source_child_a, source_child_b],
            "/deals/folder/abcd/nested-a": [],
            "/deals/folder/abcd/nested-b": [],
        }.get(provider._resolve_path(folder_path), []),
    )

    with pytest.raises(Exception, match="folder tree has 3 nodes, safety limit is 2"):
        provider.copy_item(
            "/folder/abcd",
            "/folder/abcd_copy",
            BridgeAuthContext(mode="credentials", username="user", password="pass"),
        )

    client.create_node.assert_not_called()


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


def test_download_item_rejects_payload_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _make_provider(
        monkeypatch,
        client,
        config={
            "doc_library": "/deals",
            "download": {"maxBase64Bytes": 3},
        },
    )
    monkeypatch.setattr(
        provider,
        "_query_single_node",
        lambda path, auth, include_content=False: {
            "uuid": "node-1",
            "name": "sample.txt",
            "path": "/deals/folder/sample.txt",
            "nodeType": "ctbd:baseDoc",
            "content": "dGVzdA==",
            "mimeType": "text/plain",
        },
    )

    with pytest.raises(Exception, match="payload size"):
        provider.download_item(
            "/folder/sample.txt",
            BridgeAuthContext(mode="credentials", username="user", password="pass"),
        )


def test_download_item_folder_rejects_tree_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _make_provider(
        monkeypatch,
        client,
        config={
            "doc_library": "/deals",
            "download": {"maxNodes": 2},
        },
    )
    monkeypatch.setattr(
        provider,
        "_query_single_node",
        lambda path, auth, include_content=False: {
            "uuid": "folder-1",
            "name": "folder",
            "path": "/deals/folder",
            "nodeType": "com.onlio.edocat.BaseFolder",
        },
    )
    monkeypatch.setattr(provider, "_count_folder_tree_nodes", lambda folder_path, auth: 3)

    with pytest.raises(Exception, match="folder tree has 3 nodes, safety limit is 2"):
        provider.download_item(
            "/folder",
            BridgeAuthContext(mode="credentials", username="user", password="pass"),
        )


def test_download_item_folder_requires_zip_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _make_provider(monkeypatch, client)
    monkeypatch.setattr(
        provider,
        "_query_single_node",
        lambda path, auth, include_content=False: {
            "uuid": "folder-1",
            "name": "folder",
            "path": "/deals/folder",
            "nodeType": "com.onlio.edocat.BaseFolder",
        },
    )
    monkeypatch.setattr(provider, "_count_folder_tree_nodes", lambda folder_path, auth: 1)

    with pytest.raises(Exception, match="Set download.zipEndpoint to enable server-side ZIP download"):
        provider.download_item(
            "/folder",
            BridgeAuthContext(mode="credentials", username="user", password="pass"),
        )


def test_download_item_folder_uses_zip_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _make_provider(
        monkeypatch,
        client,
        config={
            "doc_library": "/deals",
            "download": {
                "maxNodes": 10,
                "zipEndpoint": "/share/proxy/alfresco/api/internal/downloads?Alfresco-CSRFToken=test",
                "zipMethod": "POST",
            },
        },
    )
    monkeypatch.setattr(
        provider,
        "_query_single_node",
        lambda path, auth, include_content=False: {
            "uuid": "folder-1",
            "name": "folder",
            "path": "/deals/folder",
            "nodeType": "com.onlio.edocat.BaseFolder",
        },
    )
    monkeypatch.setattr(provider, "_count_folder_tree_nodes", lambda folder_path, auth: 3)

    result = provider.download_item(
        "/folder",
        BridgeAuthContext(mode="credentials", username="user", password="pass"),
    )

    assert result.success is True
    assert result.mime_type == "application/zip"
    assert result.content_base64 == base64.b64encode(b"PK\x03\x04").decode("ascii")
    client.request_bytes.assert_called_once()




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
    assert item.path == "/folder/target.pdf"


def test_stat_item_missing_leaf_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.query_nodes.return_value = {"nodes": []}
    provider = _make_provider(monkeypatch, client)

    item = provider.stat_item("/folder/missing.pdf", BridgeAuthContext(mode="credentials", username="user", password="pass"))

    assert item is None


def test_stat_item_propagates_upstream_query_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.query_nodes.side_effect = Exception("upstream timeout")
    provider = _make_provider(monkeypatch, client)

    with pytest.raises(ProviderOperationError, match="query failed"):
        provider.stat_item("/folder/file.txt", BridgeAuthContext(mode="credentials", username="user", password="pass"))


def test_stat_item_maps_http_401_to_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.query_nodes.side_effect = HTTPError(
        url="https://example.test/api/v1/node/query",
        code=401,
        msg="Unauthorized",
        hdrs=None,
        fp=None,
    )
    provider = _make_provider(monkeypatch, client)

    with pytest.raises(AuthenticationError, match="access denied"):
        provider.stat_item("/folder/file.txt", BridgeAuthContext(mode="credentials", username="user", password="pass"))


def test_stat_item_resolves_folder_from_parent_query_when_leaf_query_returns_children(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()

    def fake_query_nodes(path: str, username: str | None = None, password: str | None = None, include_content: bool = False) -> dict[str, object]:
        if path == "deals/folder/bambule":
            return {
                "nodes": [
                    {
                        "uuid": "file-1",
                        "name": "ptd_final_strom.csv",
                        "path": "/deals/folder/bambule",
                        "nodeType": "ctbd:baseDoc",
                    }
                ]
            }
        if path == "deals/folder":
            return {
                "nodes": [
                    {
                        "uuid": "folder-1",
                        "name": "bambule",
                        "path": "/deals/folder",
                        "nodeType": "ctfd:baseFolder",
                    }
                ]
            }
        return {"nodes": []}

    client.query_nodes.side_effect = fake_query_nodes
    provider = _make_provider(monkeypatch, client)

    item = provider.stat_item("/folder/bambule", BridgeAuthContext(mode="credentials", username="user", password="pass"))

    assert item is not None
    assert item.id == "folder-1"
    assert item.name == "bambule"
    assert item.path == "/folder/bambule"
    assert item.is_folder is True


def test_rename_item_does_not_target_child_with_same_name(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()

    def fake_query_nodes(path: str, username: str | None = None, password: str | None = None, include_content: bool = False) -> dict[str, object]:
        if path == "deals/parent":
            # Upstream query can return descendants; child has the same name as target node.
            return {
                "nodes": [
                    {"uuid": "child-1", "name": "parent", "path": "/deals/parent/parent", "nodeType": "ctfd:baseFolder"},
                ]
            }
        if path == "deals":
            return {
                "nodes": [
                    {"uuid": "parent-1", "name": "parent", "path": "/deals/parent", "nodeType": "ctfd:baseFolder"},
                ]
            }
        return {"nodes": []}

    client.query_nodes.side_effect = fake_query_nodes
    provider = _make_provider(monkeypatch, client)

    result = provider.rename_item(
        "/parent",
        "/renamed",
        BridgeAuthContext(mode="credentials", username="user", password="pass"),
    )

    assert result.success is True
    client.update_node.assert_called_once_with(
        {"uuid": "parent-1", "name": "renamed"},
        username="user",
        password="pass",
    )