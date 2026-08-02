from __future__ import annotations

# pyright: reportMissingTypeStubs=false

from typing import Any
from urllib.error import HTTPError

import pytest

import dms_provider_bridge.drivers.alfresco as alfresco_provider_module  # type: ignore[import-untyped]
from dms_provider_bridge.models.bridge import BridgeAuthContext  # type: ignore[import-untyped]
from dms_provider_bridge.drivers.alfresco import AlfrescoProvider  # type: ignore[import-untyped]
from dms_provider_bridge.core.errors import AuthenticationError, ConnectionOperationError  # type: ignore[import-untyped]


pytestmark = pytest.mark.unit


class FakeClient:
    def __init__(self) -> None:
        self.create_child_node_calls: list[dict[str, Any]] = []
        self.download_node_content_calls: list[dict[str, Any]] = []
        self.move_node_calls: list[dict[str, Any]] = []
        self.copy_node_calls: list[dict[str, Any]] = []
        self.update_node_content_calls: list[dict[str, Any]] = []
        self.children_by_name: dict[tuple[str, str], dict | None] = {}
        self.node_details: dict[str, dict] = {}
        self.search_calls: list[dict[str, Any]] = []
        self.search_response: dict[str, Any] = {"list": {"entries": [], "pagination": {"totalItems": 0}}}

    def search_nodes_url(self) -> str:
        return "https://example.test/search"

    def search_nodes(self, ticket: str, query: str, max_items: int = 200, skip_count: int = 0) -> dict:
        self.search_calls.append({"ticket": ticket, "query": query, "max_items": max_items, "skip_count": skip_count})
        return self.search_response

    def node_create_child_url(self, parent_id: str) -> str:
        return f"https://example.test/repo/nodes/{parent_id}/children"

    def basic_auth_token(self, username: str, password: str) -> str:
        return "ticket-a"

    def create_child_node(self, ticket: str, parent_id: str, name: str, is_folder: bool = False, content_base64: str | None = None, source_path: str | None = None) -> dict:
        self.create_child_node_calls.append(
            {
                "ticket": ticket,
                "parent_id": parent_id,
                "name": name,
                "is_folder": is_folder,
                "content_base64": content_base64,
                "source_path": source_path,
            }
        )
        return {"entry": {"id": "created-1"}}

    def child_by_name(self, ticket: str, parent_id: str, name: str) -> dict | None:
        _ = ticket
        return self.children_by_name.get((parent_id, name))

    def update_node_content(
        self,
        ticket: str,
        node_id: str,
        file_name: str,
        content_base64: str | None = None,
        source_path: str | None = None,
        major_version: bool = False,
        comment: str | None = None,
    ) -> dict:
        self.update_node_content_calls.append(
            {
                "ticket": ticket,
                "node_id": node_id,
                "file_name": file_name,
                "content_base64": content_base64,
                "source_path": source_path,
                "major_version": major_version,
                "comment": comment,
            }
        )
        version = "2.0" if major_version else "1.1"
        self.node_details[node_id] = {
            "id": node_id,
            "name": file_name,
            "modifiedAt": "2026-06-10T12:34:56.000+0000",
            "modifiedByUser": {"id": "merhautr", "displayName": "Meri"},
            "properties": {"cm:versionLabel": version, "cm:versionType": "MAJOR" if major_version else "MINOR"},
        }
        return {"entry": self.node_details[node_id]}

    def node_content_url(self, node_id: str) -> str:
        return f"https://example.test/repo/nodes/{node_id}/content"

    def get_node(self, ticket: str, node_id: str, include: list[str] | None = None) -> dict:
        _ = ticket
        _ = include
        return {"entry": self.node_details.get(node_id, {"id": node_id, "name": "sample.txt"})}

    def node_move_url(self, node_id: str) -> str:
        return f"https://example.test/repo/nodes/{node_id}/move"

    def node_copy_url(self, node_id: str) -> str:
        return f"https://example.test/repo/nodes/{node_id}/copy"

    def normalize_path(self, path: str) -> str:
        value = path.strip() or "/"
        if not value.startswith("/"):
            value = f"/{value}"
        return value.rstrip("/") or "/"

    def parent_path(self, path: str) -> str:
        normalized = self.normalize_path(path)
        if normalized == "/":
            return "/"
        parent = normalized.rsplit("/", 1)[0]
        return parent or "/"

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

    def copy_node(self, ticket: str, node_id: str, target_parent_id: str, name: str | None = None) -> dict:
        self.copy_node_calls.append(
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
    monkeypatch.setattr(alfresco_provider_module, "load_driver_config", lambda name: {"doc_library": "/deals"})
    monkeypatch.setattr(alfresco_provider_module.AlfrescoClient, "from_config", lambda config: fake_client)
    provider = AlfrescoProvider()
    provider.client = fake_client  # type: ignore[assignment]
    return provider


def _provider_with_config(monkeypatch: pytest.MonkeyPatch, config: dict[str, Any], client: FakeClient | None = None) -> AlfrescoProvider:
    fake_client = client or FakeClient()
    monkeypatch.setattr(alfresco_provider_module, "load_driver_config", lambda name: config)
    monkeypatch.setattr(alfresco_provider_module.AlfrescoClient, "from_config", lambda cfg: fake_client)
    provider = AlfrescoProvider()
    provider.client = fake_client  # type: ignore[assignment]
    return provider


def test_search_items_uses_native_search_and_filters_root(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.search_response = {
        "list": {
            "entries": [
                {"entry": {"id": "1", "name": "steam.docx", "path": {"name": "/projects"}}},
                {"entry": {"id": "2", "name": "other.docx", "path": {"name": "/other"}}},
            ],
            "pagination": {"totalItems": 2},
        }
    }
    provider = _provider(monkeypatch, client)
    monkeypatch.setattr(provider, "_ticket", lambda auth: "ticket-a")

    result = provider.search_items('steam "DN50"', "/projects", 20, None)

    assert [item.name for item in result.items] == ["steam.docx"]
    assert result.truncated is True
    assert client.search_calls[0]["max_items"] == 20
    assert '\\"DN50\\"' in client.search_calls[0]["query"]


def test_search_capability_is_native_full_text(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch)
    assert provider.search_capabilities() == {"supported": True, "mode": "native_full_text", "max_results": 100}


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
            "source_path": None,
        }
    ]


def test_upload_item_existing_document_requires_versioning_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.children_by_name[("node-parent-1", "sample.txt")] = {
        "id": "node-existing-1",
        "name": "sample.txt",
        "properties": {"cm:versionLabel": "1.4"},
    }
    client.node_details["node-existing-1"] = {
        "id": "node-existing-1",
        "name": "sample.txt",
        "createdAt": "2026-06-01T10:00:00.000+0000",
        "createdByUser": {"id": "merhautr"},
        "modifiedAt": "2026-06-02T11:00:00.000+0000",
        "modifiedByUser": {"id": "merhautr"},
        "properties": {"cm:versionLabel": "1.4", "cm:versionType": "MINOR"},
    }
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

    with pytest.raises(alfresco_provider_module.VersionRequiredError) as exc_info:
        provider.upload_item(
            "/contracts",
            "sample.txt",
            content_base64="dGVzdA==",
            auth=BridgeAuthContext(mode="credentials", username="user", password="pass"),
        )

    assert exc_info.value.metadata["action"] == "version_required"
    assert exc_info.value.metadata["current_version"] == "1.4"
    assert exc_info.value.metadata["current_version_type"] == "MINOR"
    assert exc_info.value.metadata["current_modified_at"] == "2026-06-02T11:00:00.000+0000"
    assert exc_info.value.metadata["current_modified_by"] == "merhautr"
    assert client.create_child_node_calls == []
    assert client.update_node_content_calls == []


def test_upload_item_existing_document_updates_content_as_new_minor_version(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    client.children_by_name[("node-parent-1", "sample.txt")] = {
        "id": "node-existing-1",
        "name": "sample.txt",
        "properties": {"cm:versionLabel": "1.4"},
    }
    client.node_details["node-existing-1"] = {
        "id": "node-existing-1",
        "name": "sample.txt",
        "createdAt": "2026-06-01T10:00:00.000+0000",
        "createdByUser": {"id": "merhautr"},
        "modifiedAt": "2026-06-02T11:00:00.000+0000",
        "modifiedByUser": {"id": "merhautr"},
        "properties": {"cm:versionLabel": "1.4", "cm:versionType": "MINOR"},
    }
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
        auth=BridgeAuthContext(mode="credentials", username="user", password="pass"),
        versioning={"mode": "version", "majorVersion": False, "comment": "TC upload"},
    )

    assert result.success is True
    assert result.metadata is not None
    assert result.metadata["action"] == "version"
    assert result.metadata["current_version"] == "1.4"
    assert result.metadata["version"] == "1.1"
    assert result.metadata["version_type"] == "MINOR"
    assert result.metadata["changed_at"] == "2026-06-10T12:34:56.000+0000"
    assert result.metadata["changed_by"] == "merhautr"
    assert client.create_child_node_calls == []
    assert client.update_node_content_calls == [
        {
            "ticket": "ticket-a",
            "node_id": "node-existing-1",
            "file_name": "sample.txt",
            "content_base64": "dGVzdA==",
            "source_path": None,
            "major_version": False,
            "comment": "TC upload",
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


def test_copy_item_allows_new_destination_leaf_that_does_not_yet_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _provider_with_config(monkeypatch, {"doc_library": "/deals"}, client)

    monkeypatch.setattr(provider, "_ticket", lambda auth: "ticket-a")

    def fake_resolve(path: str, ticket: str | None = None, strict: bool = False) -> dict[str, str]:
        if path.endswith("source.txt"):
            assert strict is True
            return {
                "path": "/deals/contracts/source.txt",
                "node_id": "node-source-1",
                "parent_path": "/deals/contracts",
                "parent_id": "node-parent-1",
                "name": "source.txt",
            }

        if path == "/contracts":
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

    result = provider.copy_item(
        "/contracts/source.txt",
        "/contracts/copied.txt",
        auth=BridgeAuthContext(mode="credentials", username="user", password="pass"),
    )

    assert result.success is True
    assert result.destination == "/contracts/copied.txt"
    assert client.copy_node_calls == [
        {
            "ticket": "ticket-a",
            "node_id": "node-source-1",
            "target_parent_id": "node-parent-1",
            "name": "copied.txt",
        }
    ]


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

    with pytest.raises(ConnectionOperationError, match="download failed"):
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
            "source_path": None,
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


def test_make_dir_http_409_conflict_is_treated_as_success(monkeypatch: pytest.MonkeyPatch) -> None:
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

    def _raise_409(*args, **kwargs):
        raise HTTPError(url="https://example.test", code=409, msg="Conflict", hdrs=None, fp=None)

    monkeypatch.setattr(client, "create_child_node", _raise_409)

    result = provider.make_dir(
        "/contracts/new-folder",
        auth=BridgeAuthContext(mode="credentials", username="user", password="pass"),
    )

    assert result.success is True
    assert result.operation == "mkdir"
    assert result.message is not None
    assert "status=exists" in result.message


def test_item_from_entry_maps_modified_and_read_only_metadata(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = _provider(monkeypatch, FakeClient())

    item = provider._item_from_entry(
        {
            "id": "node-1",
            "name": "report.docx",
            "path": {"name": "/deals/reports/report.docx"},
            "isFolder": False,
            "modifiedAt": "2026-06-03T08:55:12.123Z",
            "properties": {"cm:lockType": "WRITE_LOCK", "cm:versionLabel": "1.7", "cm:versionType": "MAJOR"},
            "content": {"sizeInBytes": 123, "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
        }
    )

    assert item.modified_at == "2026-06-03T08:55:12.123Z"
    assert item.is_read_only is True
    assert item.version_label == "1.7"
    assert item.version_type == "MAJOR"


def test_list_items_retries_once_after_ticket_expiration(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _provider_with_config(monkeypatch, {"doc_library": "/deals"}, client)
    auth = BridgeAuthContext(mode="credentials", username="user", password="pass")

    monkeypatch.setattr(provider, "_runtime_credentials", lambda _auth: ("user", "pass", "expired-ticket"))
    monkeypatch.setattr(client, "create_ticket", lambda username, password: "fresh-ticket", raising=False)

    calls: list[str] = []

    def fake_resolve(path: str, ticket: str | None = None, strict: bool = False) -> dict[str, str]:
        calls.append(f"resolve:{ticket}")
        return {
            "path": "/deals/contracts",
            "node_id": "node-parent-1",
            "parent_path": "/deals",
            "parent_id": "node-root-1",
            "name": "contracts",
        }

    def fake_get_children(ticket: str, node_id: str, max_items: int = 200, skip_count: int = 0) -> dict:
        calls.append(f"children:{ticket}")
        if ticket == "expired-ticket":
            raise HTTPError(url="https://example.test", code=401, msg="Unauthorized", hdrs=None, fp=None)
        return {"list": {"entries": []}}

    monkeypatch.setattr(provider, "_resolve_path", fake_resolve)
    monkeypatch.setattr(client, "get_children", fake_get_children, raising=False)

    result = provider.list_items("/contracts", auth)

    assert result.total == 0
    assert "children:expired-ticket" in calls
    assert "children:fresh-ticket" in calls


def test_list_items_maps_expired_ticket_without_refresh_to_auth_error(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    provider = _provider_with_config(monkeypatch, {"doc_library": "/deals"}, client)
    auth = BridgeAuthContext(mode="credentials", username="user", password="pass")

    monkeypatch.setattr(provider, "_runtime_credentials", lambda _auth: (None, None, "expired-ticket"))
    monkeypatch.setattr(client, "create_ticket", lambda username, password: "fresh-ticket", raising=False)

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

    def always_unauthorized(ticket: str, node_id: str, max_items: int = 200, skip_count: int = 0) -> dict:
        raise HTTPError(url="https://example.test", code=401, msg="Unauthorized", hdrs=None, fp=None)

    monkeypatch.setattr(client, "get_children", always_unauthorized, raising=False)

    with pytest.raises(AuthenticationError, match="access denied"):
        provider.list_items("/contracts", auth)

