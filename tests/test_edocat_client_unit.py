from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import pytest

import edocat_bridge.clients.edocat_client as edocat_client_module  # type: ignore[import-untyped]
from edocat_bridge.clients.edocat_client import EdocatClient  # type: ignore[import-untyped]


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
