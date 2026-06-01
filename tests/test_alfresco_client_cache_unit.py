from __future__ import annotations

# pyright: reportMissingTypeStubs=false

import pytest

from edocat_bridge.clients.alfresco_client import AlfrescoClient
from edocat_bridge.providers.alfresco import AlfrescoProvider


pytestmark = pytest.mark.unit


def _client() -> AlfrescoClient:
    return AlfrescoClient(
        base_url="https://example.test",
        api_roots={"search_root": "/search", "repo_root": "/repo"},
        endpoints={"search": "/search", "nodes": "/nodes", "people_me": "/people/-me-"},
        doc_library="/app:company_home/st:sites/cm:deals/cm:documentLibrary",
    )


def test_resolve_doc_library_node_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    calls = {"count": 0}

    def fake_search(self: AlfrescoClient, ticket: str, query: str) -> dict | None:
        calls["count"] += 1
        return {"id": "doclib-1", "name": "documentLibrary"}

    monkeypatch.setattr(AlfrescoClient, "first_search_entry", fake_search)

    first = client.resolve_doc_library_node("ticket-a")
    second = client.resolve_doc_library_node("ticket-a")

    assert first is not None
    assert second is not None
    assert first.get("id") == "doclib-1"
    assert second.get("id") == "doclib-1"
    assert calls["count"] == 1


def test_child_by_name_uses_cache_case_insensitive(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    calls = {"count": 0}

    def fake_children(self: AlfrescoClient, ticket: str, parent_id: str, max_items: int = 200, skip_count: int = 0) -> dict:
        calls["count"] += 1
        return {
            "list": {
                "entries": [
                    {"entry": {"id": "n-1", "name": "Upload"}},
                ]
            }
        }

    monkeypatch.setattr(AlfrescoClient, "get_children", fake_children)

    first = client.child_by_name("ticket-a", "parent-1", "upload")
    second = client.child_by_name("ticket-a", "parent-1", "UPLOAD")

    assert first is not None
    assert second is not None
    assert first.get("id") == "n-1"
    assert second.get("id") == "n-1"
    assert calls["count"] == 1


def test_resolve_node_by_relative_path_uses_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    child_calls = {"count": 0}

    def fake_doclib(self: AlfrescoClient, ticket: str) -> dict:
        return {"id": "root-1", "name": "documentLibrary"}

    monkeypatch.setattr(AlfrescoClient, "resolve_doc_library_node", fake_doclib)

    def fake_child_by_name(self: AlfrescoClient, ticket: str, parent_id: str, segment: str) -> dict | None:
        child_calls["count"] += 1
        if parent_id == "root-1" and segment == "A":
            return {"id": "a-1", "name": "A"}
        if parent_id == "a-1" and segment == "B":
            return {"id": "b-1", "name": "B"}
        return None

    monkeypatch.setattr(AlfrescoClient, "child_by_name", fake_child_by_name)

    first = client.resolve_node_by_relative_path("ticket-a", "/A/B")
    second = client.resolve_node_by_relative_path("ticket-a", "/A/B")

    assert first is not None
    assert second is not None
    assert first.get("id") == "b-1"
    assert second.get("id") == "b-1"
    assert child_calls["count"] == 2


def test_create_child_node_uses_configured_node_types(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    client.node_types = {"folder": ["custom:folder"], "file": ["custom:file"]}

    captured: dict[str, object] = {}

    def fake_request_json(self: AlfrescoClient, method: str, url: str, headers: dict[str, str] | None = None, payload: dict | None = None, timeout: int = 30) -> dict:
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload or {}
        return {"entry": {"id": "created-1"}}

    monkeypatch.setattr(AlfrescoClient, "_request_json", fake_request_json)

    client.create_child_node("ticket-a", "parent-1", "new-folder", is_folder=True)
    assert captured["method"] == "POST"
    folder_payload = captured["payload"]
    assert isinstance(folder_payload, dict)
    assert folder_payload["nodeType"] == "custom:folder"

    client.create_child_node("ticket-a", "parent-1", "new-file.txt", is_folder=False)
    file_payload = captured["payload"]
    assert isinstance(file_payload, dict)
    assert file_payload["nodeType"] == "custom:file"


def test_alfresco_stat_missing_file_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = AlfrescoProvider()

    monkeypatch.setattr(provider, "_ticket", lambda auth: "ticket-a")
    monkeypatch.setattr(provider, "_live_node", lambda path, auth, ticket=None: None)
    monkeypatch.setattr(
        provider,
        "_resolve_path",
        lambda path, ticket=None, strict=False: {
            "path": "/deals/folder/welcome.pdf",
            "node_id": "node-1",
            "parent_path": "/deals/folder",
            "parent_id": "parent-1",
            "name": "welcome.pdf",
        },
    )
    monkeypatch.setattr(AlfrescoClient, "child_by_name", lambda self, ticket, parent_id, name: None)

    result = provider.stat_item("/folder/welcome.pdf")

    assert result is None