from __future__ import annotations

from unittest.mock import Mock

import pytest

import edocat_bridge.services.bridge_service as bridge_service_module
from edocat_bridge.models.bridge import BridgeAuthContext
from edocat_bridge.models.item import DmsItem
from edocat_bridge.models.operation import OperationResult


pytestmark = pytest.mark.unit


class DummyProvider:
    def __init__(self, name: str, config: dict | None = None) -> None:
        self.name = name
        self.config = config or {}
        self.upstream_auth_scheme = "none"
        self.copy_item = Mock()
        self.download_item = Mock()
        self.upload_item = Mock()
        self.stat_item = Mock()

    def bridge_endpoint_for(self, operation: str) -> str | None:
        return f"https://example.test/{self.name}/{operation}"


def _auth() -> BridgeAuthContext:
    return BridgeAuthContext(mode="credentials", username="user", password="pass")


def test_copy_path_cross_provider_fso_to_edocat_uses_download_and_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("fso")
    dst_provider = DummyProvider("edocat", config={"transfer": {"maxBase64Bytes": 1024 * 1024}})

    src_provider.stat_item.return_value = DmsItem(id="f-1", name="source.txt", path="/source.txt", is_folder=False)
    src_provider.download_item.return_value = OperationResult(
        success=True,
        operation="download",
        provider="fso",
        source="/source.txt",
        content_base64="dGVzdA==",
        mime_type="text/plain",
        size=4,
    )
    dst_provider.upload_item.return_value = OperationResult(
        success=True,
        operation="upload",
        provider="edocat",
        source="source.txt",
        destination="/target.txt",
        message="upload-ok",
    )

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (src_provider, type("P", (), {"path": "/source.txt"})())
        if path == "fso:/source.txt"
        else (dst_provider, type("P", (), {"path": "/target/target.txt"})()),
    )

    response = bridge_service_module.copy_path("fso:/source.txt", "edocat:/target/target.txt", _auth())

    assert response.ok is True
    assert isinstance(response.data, dict)
    assert response.data["operation"] == "copy"
    assert response.data["provider"] == "edocat"
    src_provider.download_item.assert_called_once_with("/source.txt", _auth())
    dst_provider.upload_item.assert_called_once_with(
        "/target",
        "target.txt",
        content_base64="dGVzdA==",
        overwrite=False,
        auth=_auth(),
    )


def test_copy_path_cross_provider_rejects_payload_over_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("fso")
    dst_provider = DummyProvider("edocat", config={"transfer": {"maxBase64Bytes": 4}})

    src_provider.stat_item.return_value = DmsItem(id="f-1", name="source.txt", path="/source.txt", is_folder=False)
    src_provider.download_item.return_value = OperationResult(
        success=True,
        operation="download",
        provider="fso",
        source="/source.txt",
        content_base64="dGVzdA==",
        size=5,
    )

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (src_provider, type("P", (), {"path": "/source.txt"})())
        if path == "fso:/source.txt"
        else (dst_provider, type("P", (), {"path": "/target/target.txt"})()),
    )

    response = bridge_service_module.copy_path("fso:/source.txt", "edocat:/target/target.txt", _auth())

    assert response.ok is False
    assert "exceeds limit" in (response.message or "")
    dst_provider.upload_item.assert_not_called()


def test_copy_path_cross_provider_rejects_unsupported_direction(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("edocat")
    dst_provider = DummyProvider("fso")

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (src_provider, type("P", (), {"path": "/source.txt"})())
        if path == "edocat:/source.txt"
        else (dst_provider, type("P", (), {"path": "/target.txt"})()),
    )

    response = bridge_service_module.copy_path("edocat:/source.txt", "fso:/target.txt", _auth())

    assert response.ok is False
    assert response.error_code == bridge_service_module.WfxErrorCode.NOT_SUPPORTED
    assert "only for fso -> edocat" in (response.message or "")
