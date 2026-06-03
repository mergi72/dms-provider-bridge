from __future__ import annotations

# pyright: reportMissingTypeStubs=false

from typing import Any
from urllib.error import HTTPError

import pytest

import edocat_bridge.providers.alfresco as alfresco_provider_module  # type: ignore[import-untyped]
from edocat_bridge.models.bridge import BridgeAuthContext  # type: ignore[import-untyped]
from edocat_bridge.providers.alfresco import AlfrescoProvider  # type: ignore[import-untyped]
from edocat_bridge.core.errors import AuthenticationError  # type: ignore[import-untyped]


pytestmark = pytest.mark.unit


class FakeClient:
    def __init__(self) -> None:
        self.create_child_node_calls: list[dict[str, Any]] = []
        self.download_node_content_calls: list[dict[str, Any]] = []
        self.move_node_calls: list[dict[str, Any]] = []

    def node_create_child_url(self, parent_id: str) -> str:
        return f"https://example.test/repo/nodes/{parent_id}/children"

    def basic_auth_token(self, username: str, password: str) -> str:
        return "ticket-a"

    def create_child_node(self, ticket: str, parent_id: str, name: str, is_folder: bool = False, content_base64: str | None = None) -> dict:
        self.create_child_node_calls.append(
            {
                "ticket": ticket,
                "parent_id": parent_id,
                "name": name,
                "is_folder": is_folder,
                "content_base64": content_base64,
            }
        )
        return {"entry": {"id": "created-1"}}

    def node_content_url(self, node_id: str) -> str:
        return f"https://example.test/repo/nodes/{node_id}/content"

    def node_move_url(self, node_id: str) -> str:
        return f"https://example.test/repo/nodes/{node_id}/move"

    def normalize_path(self, path: str) -> str:
        value = path.strip() or "/"
        if not value.startswith("/"):
            value = f"/{value}"
        return value.rstrip("/") or "/"

    def download_node_content(self, ticket: str, node_id: str, max_bytes: int | None = None) -> tuple[bytes, str | None]:
        self.download_node_content_calls.append(
            {
                "ticket": ticket,
                "node_id": node_id,
                "max_bytes": max_bytes,
            }
        )
        if isinstance(max_bytes, int) and max_bytes < 4:
            raise ValueError("Alfresco download payload exceeds limit")
        return (b"test", "application/octet-stream")

    def move_node(self, ticket: str, node_id: str, target_parent_id: str, name: str | None = None) -> dict:
        self.move_node_calls.append(
            {
                "ticket": ticket,
                "node_id": node_id,
                "target_parent_id": target_parent_id,
                "name": name,
            }
        )
        return {"entry": {"id": node_id, "name": name or ""}}


def _provider(monkeypatch: pytest.MonkeyPatch, client: FakeClient | None = None) -> AlfrescoProvider:
    fake_client = client or FakeClient()
    monkeypatch.setattr(alfresco_provider_module, "load_provider_config", lambda name: {"doc_library": "/deals"})
    monkeypatch.setattr(alfresco_provider_module.AlfrescoClient, "from_config", lambda config: fake_client)
    provider = AlfrescoProvider()
    provider.client = fake_client  # type: ignore[assignment]
    return provider


def _provider_with_config(monkeypatch: pytest.MonkeyPatch, config: dict[str, Any], client: FakeClient | None = None) -> AlfrescoProvider:
    fake_client = client or FakeClient()
    monkeypatch.setattr(alfresco_provider_module, "load_provider_config", lambda name: config)
    monkeypatch.setattr(alfresco_provider_module.AlfrescoClient, "from_config", lambda cfg: fake_client)
    provider = AlfrescoProvider()
    provider.client = fake_client  # type: ignore[assignment]
    return provider


def test_upload_item_passes_content_base64_to_client(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _provider(monkeypatch, client)

    monkeypatch.setattr(provider, "_ticket", lambda auth: "ticket-a")
    monkeypatch.setattr(
        provider,
        "_resolve_path",
        lambda path, ticket=None, strict=False: {
            "path": "/deals/contracts",
            "node_id": "node-parent-1",
            "parent_path": "/deals",
            "parent_id": "node-root-1",
            "name": "contracts",
        },
    )

    result = provider.upload_item(
        "/contracts",
        "sample.txt",
        content_base64="dGVzdA==",
        overwrite=False,
        auth=BridgeAuthContext(mode="credentials", username="user", password="pass"),
    )

    assert result.success is True
    assert result.destination == "/deals/contracts/sample.txt"
    assert client.create_child_node_calls == [
        {
            "ticket": "ticket-a",
            "parent_id": "node-parent-1",
            "name": "sample.txt",
            "is_folder": False,
            "content_base64": "dGVzdA==",
        }
    ]


def test_rename_item_allows_new_destination_leaf_that_does_not_yet_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _provider_with_config(monkeypatch, {"doc_library": "/deals"}, client)

    monkeypatch.setattr(provider, "_ticket", lambda auth: "ticket-a")
    monkeypatch.setattr(
        provider,
        "_resolve_path",
        lambda path, ticket=None, strict=False: (
            {
                "path": "/deals/folder/old.txt",
                "node_id": "node-old",
                "parent_path": "/deals/folder",
                "parent_id": "node-parent-1",
                "name": "old.txt",
            }
            if path.endswith("old.txt")
            else {
                "path": "/deals/folder/new.txt",
                "node_id": "node-missing",
                "parent_path": "/deals/folder",
                "parent_id": "node-parent-1",
                "name": "new.txt",
            }
        ),
    )

    result = provider.rename_item(
        "/folder/old.txt",
        "/folder/new.txt",
        auth=BridgeAuthContext(mode="credentials", username="user", password="pass"),
    )

    assert result.success is True
    assert result.destination == "/deals/folder/new.txt"
    assert result.message is not None
    assert client.create_child_node_calls == []
    assert result.operation == "rename"


def test_download_item_passes_max_bytes_and_returns_content(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _provider_with_config(monkeypatch, {"doc_library": "/deals", "download": {"maxBase64Bytes": 8}}, client)

    monkeypatch.setattr(provider, "_ticket", lambda auth: "ticket-a")
    monkeypatch.setattr(
        provider,
        "_resolve_path",
        lambda path, ticket=None, strict=False: {
            "path": "/deals/contracts/a.txt",
            "node_id": "node-file-1",
            "parent_path": "/deals/contracts",
            "parent_id": "node-parent-1",
            "name": "a.txt",
        },
    )

    result = provider.download_item(
        "/contracts/a.txt",
        auth=BridgeAuthContext(mode="credentials", username="user", password="pass"),
    )

    assert result.success is True
    assert result.size == 4
    assert client.download_node_content_calls == [
        {
            "ticket": "ticket-a",
            "node_id": "node-file-1",
            "max_bytes": 8,
        }
    ]


def test_download_item_over_limit_raises_provider_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _provider_with_config(monkeypatch, {"doc_library": "/deals", "download": {"maxBase64Bytes": 3}}, client)

    monkeypatch.setattr(provider, "_ticket", lambda auth: "ticket-a")
    monkeypatch.setattr(
        provider,
        "_resolve_path",
        lambda path, ticket=None, strict=False: {
            "path": "/deals/contracts/a.txt",
            "node_id": "node-file-1",
            "parent_path": "/deals/contracts",
            "parent_id": "node-parent-1",
            "name": "a.txt",
        },
    )

    with pytest.raises(alfresco_provider_module.ProviderOperationError, match="download failed"):
        provider.download_item(
            "/contracts/a.txt",
            auth=BridgeAuthContext(mode="credentials", username="user", password="pass"),
        )


def test_make_dir_allows_new_destination_leaf_that_does_not_yet_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _provider_with_config(monkeypatch, {"doc_library": "/deals"}, client)

    monkeypatch.setattr(provider, "_ticket", lambda auth: "ticket-a")

    def fake_resolve(path: str, ticket: str | None = None, strict: bool = False) -> dict[str, str]:
        if path == "/contracts/new-folder":
            assert strict is False
            return {
                "path": "/deals/contracts/new-folder",
                "node_id": "missing-node",
                "parent_path": "/deals/contracts",
                "parent_id": "fallback-parent-id",
                "name": "new-folder",
            }
        if path == "/deals/contracts":
            assert strict is True
            return {
                "path": "/deals/contracts",
                "node_id": "node-parent-1",
                "parent_path": "/deals",
                "parent_id": "node-root-1",
                "name": "contracts",
            }
        raise AssertionError(f"Unexpected path: {path}")

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)

    result = provider.make_dir(
        "/contracts/new-folder",
        auth=BridgeAuthContext(mode="credentials", username="user", password="pass"),
    )

    assert result.success is True
    assert client.create_child_node_calls == [
        {
            "ticket": "ticket-a",
            "parent_id": "node-parent-1",
            "name": "new-folder",
            "is_folder": True,
            "content_base64": None,
        }
    ]


def test_make_dir_maps_http_403_to_authentication_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _provider_with_config(monkeypatch, {"doc_library": "/deals"}, client)

    monkeypatch.setattr(provider, "_ticket", lambda auth: "ticket-a")
    monkeypatch.setattr(
        provider,
        "_resolve_path",
        lambda path, ticket=None, strict=False: (
            {
                "path": "/deals/contracts/new-folder",
                "node_id": "missing-node",
                "parent_path": "/deals/contracts",
                "parent_id": "fallback-parent-id",
                "name": "new-folder",
            }
            if path == "/contracts/new-folder"
            else {
                "path": "/deals/contracts",
                "node_id": "node-parent-1",
                "parent_path": "/deals",
                "parent_id": "node-root-1",
                "name": "contracts",
            }
        ),
    )

    def _raise_403(*args, **kwargs):
        raise HTTPError(url="https://example.test", code=403, msg="Forbidden", hdrs=None, fp=None)

    monkeypatch.setattr(client, "create_child_node", _raise_403)

    with pytest.raises(AuthenticationError, match="access denied"):
        provider.make_dir(
            "/contracts/new-folder",
            auth=BridgeAuthContext(mode="credentials", username="user", password="pass"),
        )


def test_item_from_entry_maps_modified_and_read_only_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch, FakeClient())

    item = provider._item_from_entry(
        {
            "id": "node-1",
            "name": "report.docx",
            "path": {"name": "/deals/reports/report.docx"},
            "isFolder": False,
            "modifiedAt": "2026-06-03T08:55:12.123Z",
            "properties": {"cm:lockType": "WRITE_LOCK"},
            "content": {"sizeInBytes": 123, "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        }
    )

    assert item.modified_at == "2026-06-03T08:55:12.123Z"
    assert item.is_read_only is True
