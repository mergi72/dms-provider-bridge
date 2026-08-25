from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

import dms_provider_bridge.clients.edocat_client as edocat_client_module  # type: ignore[import-untyped]
from dms_provider_bridge.clients.edocat_client import EdocatClient  # type: ignore[import-untyped]


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


def test_resolve_share_url_reads_same_host_redirect_path(monkeypatch: pytest.MonkeyPatch) -> None:
    class RedirectError(HTTPError):
        pass

    class FakeOpener:
        def open(self, req, timeout=30):
            assert req.full_url == "https://example.test/share/page/browse/DIR-250566"
            assert timeout == 30
            raise RedirectError(
                req.full_url,
                302,
                "Found",
                {"Location": "../../page/site/deals/documentlibrary?path=/Shared%20Documents/Projects"},
                None,
            )

    monkeypatch.setattr(edocat_client_module.request, "build_opener", lambda *_handlers: FakeOpener())
    client = EdocatClient("https://example.test", "api", {}, "/deals")

    assert client.resolve_share_url("https://example.test/share/page/browse/DIR-250566") == "/Shared Documents/Projects"


@pytest.mark.parametrize(
    "share_url",
    [
        "https://evil.test/share/page/browse/DIR-250566",
        "https://example.test/other/DIR-250566",
        "file:///share/page/browse/DIR-250566",
    ],
)
def test_resolve_share_url_rejects_untrusted_target(share_url: str) -> None:
    client = EdocatClient("https://example.test", "api", {}, "/deals")

    with pytest.raises(ValueError):
        client.resolve_share_url(share_url)


def test_query_nodes_fetches_all_pages(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_urls: list[str] = []

    def fake_urlopen(req, timeout=30):
        del timeout
        url = str(req.full_url)
        captured_urls.append(url)
        query = parse_qs(urlparse(url).query)
        page = int(query.get("page", ["0"])[0])

        if page == 0:
            nodes = [{"uuid": f"n-{idx}"} for idx in range(100)]
        elif page == 1:
            nodes = [{"uuid": f"n-{100 + idx}"} for idx in range(20)]
        else:
            nodes = []

        return FakeResponse(json.dumps({"nodes": nodes}))

    monkeypatch.setattr(edocat_client_module.request, "urlopen", fake_urlopen)

    client = EdocatClient(
        base_url="https://example.test",
        api_root="edocat/api/v1",
        endpoints={"node": "node", "query": "node/query"},
        doc_library="/deals",
    )

    response = client.query_nodes("deals/folder", username="user", password="pass")

    assert len(response["nodes"]) == 120
    assert response["nodes"][0]["uuid"] == "n-0"
    assert response["nodes"][-1]["uuid"] == "n-119"
    assert len(captured_urls) == 2
    first_query = parse_qs(urlparse(captured_urls[0]).query)
    second_query = parse_qs(urlparse(captured_urls[1]).query)
    assert first_query["page"] == ["0"]
    assert first_query["size"] == ["100"]
    assert second_query["page"] == ["1"]
    assert second_query["size"] == ["100"]


def test_query_nodes_stops_when_api_repeats_same_page(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_urls: list[str] = []

    def fake_urlopen(req, timeout=30):
        del timeout
        url = str(req.full_url)
        captured_urls.append(url)
        nodes = [{"uuid": f"same-{idx}", "path": "deals/folder", "name": f"item-{idx}"} for idx in range(100)]
        return FakeResponse(json.dumps({"nodes": nodes}))

    monkeypatch.setattr(edocat_client_module.request, "urlopen", fake_urlopen)

    client = EdocatClient(
        base_url="https://example.test",
        api_root="edocat/api/v1",
        endpoints={"node": "node", "query": "node/query"},
        doc_library="/deals",
    )

    response = client.query_nodes("deals/folder", username="user", password="pass")

    assert len(response["nodes"]) == 100
    assert len(captured_urls) == 2


def test_query_nodes_by_uuids_uses_uuid_params_and_include_content(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_urls: list[str] = []

    def fake_urlopen(req, timeout=30):
        del timeout
        captured_urls.append(str(req.full_url))
        return FakeResponse(json.dumps({"nodes": [{"uuid": "a"}, {"uuid": "b"}]}))

    monkeypatch.setattr(edocat_client_module.request, "urlopen", fake_urlopen)

    client = EdocatClient(
        base_url="https://example.test",
        api_root="edocat/api/v1",
        endpoints={"node": "node", "query": "node/query"},
        doc_library="/deals",
    )

    response = client.query_nodes_by_uuids(["a", "b"], username="user", password="pass", include_content=True)

    assert [node["uuid"] for node in response["nodes"]] == ["a", "b"]
    query = parse_qs(urlparse(captured_urls[0]).query)
    assert query["uuids"] == ["a", "b"]
    assert query["includeContent"] == ["true"]
    assert "page" not in query
    assert "size" not in query


def test_search_nodes_posts_fts_query_without_content(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout=30):
        captured["method"] = req.get_method()
        captured["url"] = str(req.full_url)
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        captured["authorization"] = req.headers.get("Authorization")
        return FakeResponse(json.dumps({"nodes": [{"uuid": "found"}]}))

    monkeypatch.setattr(edocat_client_module.request, "urlopen", fake_urlopen)
    client = EdocatClient(
        base_url="https://example.test",
        api_root="edocat/api/v1",
        endpoints={"query": "node/query"},
        doc_library="/deals",
    )

    response = client.search_nodes('TEXT:"steam"', max_items=25, username="user", password="pass")

    assert response["nodes"] == [{"uuid": "found"}]
    assert captured["method"] == "POST"
    assert captured["url"] == "https://example.test/edocat/api/v1/node/query"
    assert captured["payload"] == {
        "query": 'TEXT:"steam"',
        "includeContent": False,
        "paging": {"maxItems": 25, "skipCount": 0},
    }
    assert str(captured["authorization"]).startswith("Basic ")


def test_search_metadata_nodes_uses_structured_tag_query(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout=30):
        captured["url"] = str(req.full_url)
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse(json.dumps({"nodes": []}))

    monkeypatch.setattr(edocat_client_module.request, "urlopen", fake_urlopen)
    client = EdocatClient(
        base_url="https://example.test",
        api_root="edocat/api/v1",
        endpoints={"search": "node/search"},
        doc_library="/deals",
    )

    client.search_metadata_nodes("TAG", None, "nod68-dps", "com.onlio.edocat.BaseFolder")

    assert captured["url"] == "https://example.test/edocat/api/v1/node/search"
    assert captured["payload"] == {
        "nodeType": "com.onlio.edocat.BaseFolder",
        "query": [["TAG", "nod68-dps"]],
        "includeContent": False,
        "paging": {"maxItems": 20, "skipCount": 0},
    }


def test_create_node_uses_upload_timeout_from_config(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_urlopen(req, timeout=30):
        captured["url"] = str(req.full_url)
        captured["timeout"] = timeout
        return FakeResponse(json.dumps({"uuid": "created"}))

    monkeypatch.setattr(edocat_client_module.request, "urlopen", fake_urlopen)

    client = EdocatClient.from_config(
        {
            "base_url": "https://example.test",
            "api": "edocat/api/v1",
            "endpoints": {"node": "node", "query": "node/query"},
            "timeouts": {"requestSeconds": 60, "uploadSeconds": 300},
        }
    )

    response = client.create_node({"name": "large.zip"}, username="user", password="pass")

    assert response["uuid"] == "created"
    assert captured["url"] == "https://example.test/edocat/api/v1/node"
    assert captured["timeout"] == 300
