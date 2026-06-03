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


def test_resolve_doc_library_node_walks_qname_children(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    child_calls = {"count": 0}

    monkeypatch.setattr(AlfrescoClient, "first_search_entry", lambda self, ticket, query: None)

    def fake_child_by_name(self: AlfrescoClient, ticket: str, parent_id: str, name: str) -> dict | None:
        child_calls["count"] += 1
        if parent_id == "-root-" and name == "app:company_home":
            return {"id": "company-home", "name": "Company Home"}
        if parent_id == "company-home" and name == "st:sites":
            return {"id": "sites-1", "name": "Sites"}
        if parent_id == "sites-1" and name == "cm:deals":
            return {"id": "deals-1", "name": "deals"}
        if parent_id == "deals-1" and name == "cm:documentLibrary":
            return {"id": "doclib-1", "name": "documentLibrary"}
        return None

    monkeypatch.setattr(AlfrescoClient, "child_by_name", fake_child_by_name)

    result = client.resolve_doc_library_node("ticket-a")

    assert result is not None
    assert result.get("id") == "doclib-1"
    assert child_calls["count"] >= 4


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


def test_create_child_node_includes_content_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()

    captured: dict[str, object] = {}

    def fail_request_json(self: AlfrescoClient, method: str, url: str, headers: dict[str, str] | None = None, payload: dict | None = None, timeout: int = 30) -> dict:
        raise AssertionError("Multipart upload path should not call _request_json.")

    monkeypatch.setattr(AlfrescoClient, "_request_json", fail_request_json)

    class _FakeResponse:
        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b'{"entry": {"id": "created-1"}}'

    def fake_urlopen(req, timeout: int = 30):
        captured["method"] = req.get_method()
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.header_items()}
        captured["body"] = req.data
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr("edocat_bridge.clients.alfresco_client.request.urlopen", fake_urlopen)

    client.create_child_node("ticket-a", "parent-1", "new-file.txt", is_folder=False, content_base64="dGVzdA==")

    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["content-type"].startswith("multipart/form-data; boundary=")

    body = captured["body"]
    assert isinstance(body, bytes)
    assert b'name="name"' in body
    assert b"new-file.txt" in body
    assert b'name="nodeType"' in body
    assert b"cm:content" in body
    assert b'name="filedata"; filename="new-file.txt"' in body
    assert b"test" in body


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


def test_move_node_invalidates_structure_cache_for_ticket(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    ticket = "ticket-a"
    ticket_key = client._ticket_key(ticket)

    path_key = f"{ticket_key}|/A/B"
    child_key = f"{ticket_key}|parent-1|new.txt"
    other_ticket_key = client._ticket_key("ticket-b")
    other_path_key = f"{other_ticket_key}|/A/B"

    client._path_cache[path_key] = {"id": "node-stale"}
    client._child_cache[child_key] = None
    client._path_cache[other_path_key] = {"id": "node-other"}

    monkeypatch.setattr(
        AlfrescoClient,
        "_request_json",
        lambda self, method, url, headers=None, payload=None, timeout=30: {"entry": {"id": "moved-1"}},
    )

    client.move_node(ticket, "node-1", "parent-1", "new.txt")

    assert path_key not in client._path_cache
    assert child_key not in client._child_cache
    assert other_path_key in client._path_cache


def test_from_config_reads_timeout_settings() -> None:
    client = AlfrescoClient.from_config(
        {
            "base_url": "https://example.test",
            "api": {"search_root": "/search", "repo_root": "/repo"},
            "endpoints": {"search": "/search", "nodes": "/nodes"},
            "doc_library": "/app:company_home/st:sites/cm:deals/cm:documentLibrary",
            "timeouts": {
                "requestSeconds": 17,
                "downloadSeconds": 41,
                "uploadSeconds": 73,
            },
        }
    )

    assert client.json_timeout == 17
    assert client.bytes_timeout == 41
    assert client.upload_timeout == 73


def test_create_child_node_uses_configured_upload_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    client.upload_timeout = 91
    captured: dict[str, object] = {}

    class _FakeResponse:
        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, exc_type, exc, tb) -> None:
            return None

        def read(self) -> bytes:
            return b'{"entry": {"id": "created-1"}}'

    def fake_urlopen(req, timeout: int = 30):
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr("edocat_bridge.clients.alfresco_client.request.urlopen", fake_urlopen)

    client.create_child_node("ticket-a", "parent-1", "new-file.txt", is_folder=False, content_base64="dGVzdA==")

    assert captured["timeout"] == 91