from __future__ import annotations

import os
from unittest.mock import Mock

import pytest

import edocat_bridge.services.bridge_service as bridge_service_module
from edocat_bridge.core.errors import AuthenticationError, ProviderOperationError
from edocat_bridge.models.bridge import BridgeAuthContext
from edocat_bridge.models.item import DmsItem
from edocat_bridge.models.listing import ListingResult
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
        self.stat_item = Mock(return_value=None)
        self.list_items = Mock()
        self.make_dir = Mock(return_value=OperationResult(success=True, operation="mkdir", provider=name))

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


def test_copy_path_cross_provider_fso_to_alfresco_uses_download_and_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("fso")
    dst_provider = DummyProvider("alfresco", config={"transfer": {"maxBase64Bytes": 1024 * 1024}})

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
        provider="alfresco",
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

    response = bridge_service_module.copy_path("fso:/source.txt", "alfresco:/target/target.txt", _auth())

    assert response.ok is True
    assert isinstance(response.data, dict)
    assert response.data["operation"] == "copy"
    assert response.data["provider"] == "alfresco"
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
    assert "only for fso -> dms providers" in (response.message or "")


def test_copy_path_cross_provider_fso_folder_creates_target_and_uploads_children(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("fso")
    dst_provider = DummyProvider("edocat", config={"transfer": {"maxBase64Bytes": 1024 * 1024, "maxNodes": 10}})

    src_provider.stat_item.return_value = DmsItem(id="d-1", name="src", path="/src", is_folder=True)
    src_provider.list_items.side_effect = lambda path, auth: {
        "/src": ListingResult(
            provider="fso",
            path="/src",
            total=2,
            items=[
                DmsItem(id="f-1", name="a.txt", path="/src/a.txt", is_folder=False, size=1),
                DmsItem(id="d-2", name="nested", path="/src/nested", is_folder=True),
            ],
        ),
        "/src/nested": ListingResult(
            provider="fso",
            path="/src/nested",
            total=1,
            items=[DmsItem(id="f-2", name="b.txt", path="/src/nested/b.txt", is_folder=False)],
        ),
    }[path]
    src_provider.download_item.side_effect = lambda path, auth: {
        "/src/a.txt": OperationResult(success=True, operation="download", provider="fso", source=path, content_base64="YQ==", size=1),
        "/src/nested/b.txt": OperationResult(success=True, operation="download", provider="fso", source=path, content_base64="Yg==", size=1),
    }[path]
    dst_provider.upload_item.return_value = OperationResult(success=True, operation="upload", provider="edocat")

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (src_provider, type("P", (), {"path": "/src"})())
        if path == "fso:/src"
        else (dst_provider, type("P", (), {"path": "/dst"})()),
    )

    response = bridge_service_module.copy_path("fso:/src", "edocat:/dst", _auth())

    assert response.ok is True
    dst_provider.make_dir.assert_any_call("/dst", _auth())
    dst_provider.make_dir.assert_any_call("/dst/nested", _auth())
    dst_provider.upload_item.assert_any_call("/dst", "a.txt", content_base64="YQ==", overwrite=False, auth=_auth())
    dst_provider.upload_item.assert_any_call("/dst/nested", "b.txt", content_base64="Yg==", overwrite=False, auth=_auth())


def test_copy_path_cross_provider_fso_folder_rejects_tree_over_node_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("fso")
    dst_provider = DummyProvider("edocat", config={"transfer": {"maxBase64Bytes": 1024 * 1024, "maxNodes": 2}})

    src_provider.stat_item.return_value = DmsItem(id="d-1", name="src", path="/src", is_folder=True)
    src_provider.list_items.side_effect = lambda path, auth: {
        "/src": ListingResult(
            provider="fso",
            path="/src",
            total=2,
            items=[
                DmsItem(id="f-1", name="a.txt", path="/src/a.txt", is_folder=False, size=1),
                DmsItem(id="d-2", name="nested", path="/src/nested", is_folder=True),
            ],
        ),
        "/src/nested": ListingResult(
            provider="fso",
            path="/src/nested",
            total=0,
            items=[],
        ),
    }[path]

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (src_provider, type("P", (), {"path": "/src"})())
        if path == "fso:/src"
        else (dst_provider, type("P", (), {"path": "/dst"})()),
    )

    response = bridge_service_module.copy_path("fso:/src", "edocat:/dst", _auth())

    assert response.ok is False
    assert "source tree has" in (response.message or "")
    dst_provider.make_dir.assert_not_called()
    dst_provider.upload_item.assert_not_called()


def test_copy_path_cross_provider_fso_folder_creates_destination_chain_top_down(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("fso")
    dst_provider = DummyProvider("edocat", config={"transfer": {"maxBase64Bytes": 1024 * 1024, "maxNodes": 10}})

    src_provider.stat_item.return_value = DmsItem(id="d-1", name="src", path="/src", is_folder=True)
    src_provider.list_items.return_value = ListingResult(
        provider="fso",
        path="/src",
        total=1,
        items=[DmsItem(id="f-1", name="a.txt", path="/src/a.txt", is_folder=False)],
    )
    src_provider.download_item.return_value = OperationResult(
        success=True,
        operation="download",
        provider="fso",
        source="/src/a.txt",
        content_base64="YQ==",
        size=1,
    )
    dst_provider.upload_item.return_value = OperationResult(success=True, operation="upload", provider="edocat")

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (src_provider, type("P", (), {"path": "/src"})())
        if path == "fso:/src"
        else (dst_provider, type("P", (), {"path": "/A/B/C"})()),
    )

    response = bridge_service_module.copy_path("fso:/src", "edocat:/A/B/C", _auth())

    assert response.ok is True
    assert dst_provider.make_dir.call_args_list[0].args == ("/A", _auth())
    assert dst_provider.make_dir.call_args_list[1].args == ("/A/B", _auth())
    assert dst_provider.make_dir.call_args_list[2].args == ("/A/B/C", _auth())


def test_copy_path_cross_provider_fso_file_creates_destination_chain_top_down(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("fso")
    dst_provider = DummyProvider("edocat", config={"transfer": {"maxBase64Bytes": 1024 * 1024}})

    src_provider.stat_item.return_value = DmsItem(id="f-1", name="source.txt", path="/source.txt", is_folder=False)
    src_provider.download_item.return_value = OperationResult(
        success=True,
        operation="download",
        provider="fso",
        source="/source.txt",
        content_base64="dGVzdA==",
        size=4,
    )
    dst_provider.upload_item.return_value = OperationResult(success=True, operation="upload", provider="edocat")

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (src_provider, type("P", (), {"path": "/source.txt"})())
        if path == "fso:/source.txt"
        else (dst_provider, type("P", (), {"path": "/A/B/C/target.txt"})()),
    )

    response = bridge_service_module.copy_path("fso:/source.txt", "edocat:/A/B/C/target.txt", _auth())

    assert response.ok is True
    assert dst_provider.make_dir.call_args_list[0].args == ("/A", _auth())
    assert dst_provider.make_dir.call_args_list[1].args == ("/A/B", _auth())
    assert dst_provider.make_dir.call_args_list[2].args == ("/A/B/C", _auth())
    dst_provider.upload_item.assert_called_once_with(
        "/A/B/C",
        "target.txt",
        content_base64="dGVzdA==",
        overwrite=False,
        auth=_auth(),
    )


def test_upload_path_creates_destination_chain_top_down(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DummyProvider("edocat")
    provider.upload_item.return_value = OperationResult(success=True, operation="upload", provider="edocat")

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(bridge_service_module, "_resolve", lambda destination: (provider, type("P", (), {"path": "/A/B/C"})()))

    response = bridge_service_module.upload_path("edocat:/A/B/C", "test.txt", _auth(), content_base64="YQ==", overwrite=False)

    assert response.ok is True
    assert provider.make_dir.call_args_list[0].args == ("/A", _auth())
    assert provider.make_dir.call_args_list[1].args == ("/A/B", _auth())
    assert provider.make_dir.call_args_list[2].args == ("/A/B/C", _auth())
    provider.upload_item.assert_called_once_with("/A/B/C", "test.txt", content_base64="YQ==", source_path=None, overwrite=False, auth=_auth())


def test_upload_path_rejects_payload_over_limit_without_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DummyProvider("edocat", config={"transfer": {"maxBase64Bytes": 3}})

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(bridge_service_module, "_resolve", lambda destination: (provider, type("P", (), {"path": "/A/B/C"})()))

    response = bridge_service_module.upload_path("edocat:/A/B/C", "test.txt", _auth(), content_base64="dGVzdA==", overwrite=False)

    assert response.ok is False
    assert "exceeds limit" in (response.message or "")
    provider.make_dir.assert_not_called()
    provider.upload_item.assert_not_called()


def test_upload_path_source_path_bypasses_base64_limit(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    provider = DummyProvider("fso", config={"transfer": {"maxBase64Bytes": 3}})
    provider.upload_item.return_value = OperationResult(success=True, operation="upload", provider="fso")

    source = tmp_path / "large.bin"
    source.write_bytes(b"12345")

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(bridge_service_module, "_resolve", lambda destination: (provider, type("P", (), {"path": "/A/B/C"})()))

    response = bridge_service_module.upload_path(
        "fso:/A/B/C",
        "large.bin",
        _auth(),
        source_path=os.fspath(source),
        overwrite=False,
    )

    assert response.ok is True
    provider.upload_item.assert_called_once_with(
        "/A/B/C",
        "large.bin",
        content_base64=None,
        source_path=os.fspath(source),
        overwrite=False,
        auth=_auth(),
    )


def test_stat_path_maps_provider_authentication_error_to_access_denied(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DummyProvider("edocat")
    provider.stat_item.side_effect = AuthenticationError("eDoCat access denied for /folder: HTTP 401.")

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(bridge_service_module, "_resolve", lambda path: (provider, type("P", (), {"path": "/folder"})()))

    response = bridge_service_module.stat_path("edocat:/folder", _auth())

    assert response.ok is False
    assert response.error_code == bridge_service_module.WfxErrorCode.ACCESS_DENIED
    assert "access denied" in (response.message or "").lower()


def test_stat_path_maps_provider_operation_error_to_internal_error(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DummyProvider("edocat")
    provider.stat_item.side_effect = ProviderOperationError("eDoCat query failed for /folder: HTTP 500.")

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(bridge_service_module, "_resolve", lambda path: (provider, type("P", (), {"path": "/folder"})()))

    response = bridge_service_module.stat_path("edocat:/folder", _auth())

    assert response.ok is False
    assert response.error_code == bridge_service_module.WfxErrorCode.INTERNAL_ERROR
    assert "query failed" in (response.message or "").lower()


def test_copy_path_cross_provider_fso_folder_rejects_file_over_limit_without_operations(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("fso")
    dst_provider = DummyProvider("edocat", config={"transfer": {"maxBase64Bytes": 3, "maxNodes": 10}})

    src_provider.stat_item.return_value = DmsItem(id="d-1", name="src", path="/src", is_folder=True)
    src_provider.list_items.return_value = ListingResult(
        provider="fso",
        path="/src",
        total=1,
        items=[DmsItem(id="f-1", name="a.txt", path="/src/a.txt", is_folder=False, size=4)],
    )

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (src_provider, type("P", (), {"path": "/src"})())
        if path == "fso:/src"
        else (dst_provider, type("P", (), {"path": "/dst"})()),
    )

    response = bridge_service_module.copy_path("fso:/src", "edocat:/dst", _auth())

    assert response.ok is False
    assert "exceeds limit" in (response.message or "")
    dst_provider.make_dir.assert_not_called()
    dst_provider.upload_item.assert_not_called()
