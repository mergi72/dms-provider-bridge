from __future__ import annotations

# pyright: reportMissingTypeStubs=false

from typing import Any

import pytest

import edocat_bridge.providers.alfresco as alfresco_provider_module  # type: ignore[import-untyped]
from edocat_bridge.models.bridge import BridgeAuthContext  # type: ignore[import-untyped]
from edocat_bridge.providers.alfresco import AlfrescoProvider  # type: ignore[import-untyped]


pytestmark = pytest.mark.unit


class FakeClient:
    def __init__(self) -> None:
        self.create_child_node_calls: list[dict[str, Any]] = []

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


def _provider(monkeypatch: pytest.MonkeyPatch, client: FakeClient | None = None) -> AlfrescoProvider:
    fake_client = client or FakeClient()
    monkeypatch.setattr(alfresco_provider_module, "load_provider_config", lambda name: {"doc_library": "/deals"})
    monkeypatch.setattr(alfresco_provider_module.AlfrescoClient, "from_config", lambda config: fake_client)
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
