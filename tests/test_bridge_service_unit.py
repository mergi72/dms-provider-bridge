from __future__ import annotations

import os
from unittest.mock import Mock

import pytest

import dms_provider_bridge.services.bridge_service as bridge_service_module
from dms_provider_bridge.core.errors import AuthenticationError, ProviderOperationError
from dms_provider_bridge.models.bridge import BridgeAuthContext
from dms_provider_bridge.models.item import DmsItem
from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.models.operation import OperationResult


pytestmark = pytest.mark.unit


class DummyProvider:
    def __init__(self, name: str, config: dict | None = None) -> None:
        self.name = name
        self.config = config or {}
        self.upstream_auth_scheme = "none"
        self.copy_item = Mock()
        self.rename_item = Mock()
        self.delete_item = Mock()
        self.download_item = Mock()
        self.upload_item = Mock()
        self.stat_item = Mock(return_value=None)
        self.list_items = Mock()
        self.make_dir = Mock(return_value=OperationResult(success=True, operation="mkdir", provider=name))

    def bridge_endpoint_for(self, operation: str) -> str | None:
        return f"https://example.test/{self.name}/{operation}"


def _auth() -> BridgeAuthContext:
    return BridgeAuthContext(mode="credentials", username="user", password="pass")


def _credential_auth(credential_id: str) -> BridgeAuthContext:
    return BridgeAuthContext(mode="credentials", credential_id=credential_id)


def test_copy_path_same_provider_delegates_to_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DummyProvider("edocat")
    provider.copy_item.return_value = OperationResult(success=True, operation="copy", provider="edocat")

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(bridge_service_module, "_resolve", lambda path: (provider, type("P", (), {"path": path.split(":", 1)[1]})()))

    response = bridge_service_module.copy_path("edocat:/source.txt", "edocat:/target.txt", _auth())

    assert response.ok is True
    provider.copy_item.assert_called_once_with("/source.txt", "/target.txt", _auth())


def test_copy_path_cross_provider_downloads_and_uploads(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("edocat")
    dst_provider = DummyProvider("alfresco")
    src_provider.download_item.return_value = OperationResult(
        success=True,
        operation="download",
        provider="edocat",
        content_base64="dGVzdA==",
        size=4,
    )
    dst_provider.upload_item.return_value = OperationResult(success=True, operation="upload", provider="alfresco")

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (src_provider, type("P", (), {"path": "/source.txt"})())
        if path == "edocat:/source.txt"
        else (dst_provider, type("P", (), {"path": "/target.txt"})()),
    )

    response = bridge_service_module.copy_path("edocat:/source.txt", "alfresco:/target.txt", _auth())

    assert response.ok is True
    src_provider.copy_item.assert_not_called()
    dst_provider.copy_item.assert_not_called()
    src_provider.download_item.assert_called_once_with("/source.txt", _auth())
    dst_provider.upload_item.assert_called_once_with(
        "/",
        "target.txt",
        content_base64="dGVzdA==",
        source_path=None,
        overwrite=False,
        auth=_auth(),
    )
    assert response.metadata["transfer"] == "download-upload"


def test_copy_path_cross_provider_uses_separate_source_and_destination_auth_instances(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("edocat")
    dst_provider = DummyProvider("alfresco")
    src_provider.download_item.return_value = OperationResult(
        success=True,
        operation="download",
        provider="edocat",
        content_base64="dGVzdA==",
        size=4,
    )
    dst_provider.upload_item.return_value = OperationResult(success=True, operation="upload", provider="alfresco")
    fallback_auth = _credential_auth("fallback")
    source_auth = _credential_auth("source")
    destination_auth = _credential_auth("destination")

    def _validate(auth: BridgeAuthContext) -> BridgeAuthContext:
        auth.username = f"{auth.credential_id}-user"
        auth.password = f"{auth.credential_id}-password"
        return auth

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", _validate)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (src_provider, type("P", (), {"path": "/source.txt"})())
        if path == "edocat:/source.txt"
        else (dst_provider, type("P", (), {"path": "/target.txt"})()),
    )

    response = bridge_service_module.copy_path(
        "edocat:/source.txt",
        "alfresco:/target.txt",
        fallback_auth,
        source_auth=source_auth,
        destination_auth=destination_auth,
    )

    assert response.ok is True
    download_auth = src_provider.download_item.call_args.args[1]
    upload_auth = dst_provider.upload_item.call_args.kwargs["auth"]
    assert download_auth is not upload_auth
    assert download_auth.username == "source-user"
    assert upload_auth.username == "destination-user"
    assert source_auth.username is None
    assert destination_auth.username is None
    assert fallback_auth.username is None


def test_copy_path_cross_provider_uses_temp_file_when_inline_limit_is_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("edocat")
    dst_provider = DummyProvider("alfresco", config={"upload": {"inline": {"maxBytes": 3}}})
    src_provider.download_item.return_value = OperationResult(
        success=True,
        operation="download",
        provider="edocat",
        content_base64="MTIzNDU=",
        size=5,
    )
    dst_provider.upload_item.return_value = OperationResult(success=True, operation="upload", provider="alfresco")

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (src_provider, type("P", (), {"path": "/source.bin"})())
        if path == "edocat:/source.bin"
        else (dst_provider, type("P", (), {"path": "/target.bin"})()),
    )

    response = bridge_service_module.copy_path("edocat:/source.bin", "alfresco:/target.bin", _auth())

    assert response.ok is True
    dst_provider.upload_item.assert_called_once()
    _, file_name = dst_provider.upload_item.call_args.args[:2]
    kwargs = dst_provider.upload_item.call_args.kwargs
    assert file_name == "target.bin"
    assert kwargs["content_base64"] is None
    assert kwargs["source_path"] is not None
    assert not os.path.exists(kwargs["source_path"])


def test_rename_path_cross_provider_downloads_uploads_and_deletes(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("alfresco")
    dst_provider = DummyProvider("edocat")
    src_provider.download_item.return_value = OperationResult(
        success=True,
        operation="download",
        provider="alfresco",
        content_base64="Y29udGVudA==",
        size=7,
    )
    dst_provider.upload_item.return_value = OperationResult(success=True, operation="upload", provider="edocat")
    src_provider.delete_item.return_value = OperationResult(success=True, operation="delete", provider="alfresco")

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (src_provider, type("P", (), {"path": "/source.txt"})())
        if path == "alfresco:/source.txt"
        else (dst_provider, type("P", (), {"path": "/folder/target.txt"})()),
    )

    response = bridge_service_module.rename_path("alfresco:/source.txt", "edocat:/folder/target.txt", _auth())

    assert response.ok is True
    src_provider.rename_item.assert_not_called()
    src_provider.download_item.assert_called_once_with("/source.txt", _auth())
    dst_provider.upload_item.assert_called_once_with(
        "/folder",
        "target.txt",
        content_base64="Y29udGVudA==",
        source_path=None,
        overwrite=False,
        auth=_auth(),
    )
    src_provider.delete_item.assert_called_once_with("/source.txt", _auth())
    assert response.metadata["transfer"] == "download-upload-delete"


def test_rename_path_cross_provider_uses_source_auth_for_delete_and_destination_auth_for_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("alfresco")
    dst_provider = DummyProvider("edocat")
    src_provider.download_item.return_value = OperationResult(
        success=True,
        operation="download",
        provider="alfresco",
        content_base64="Y29udGVudA==",
        size=7,
    )
    dst_provider.upload_item.return_value = OperationResult(success=True, operation="upload", provider="edocat")
    src_provider.delete_item.return_value = OperationResult(success=True, operation="delete", provider="alfresco")

    def _validate(auth: BridgeAuthContext) -> BridgeAuthContext:
        auth.username = f"{auth.credential_id}-user"
        auth.password = f"{auth.credential_id}-password"
        return auth

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", _validate)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (src_provider, type("P", (), {"path": "/source.txt"})())
        if path == "alfresco:/source.txt"
        else (dst_provider, type("P", (), {"path": "/folder/target.txt"})()),
    )

    response = bridge_service_module.rename_path(
        "alfresco:/source.txt",
        "edocat:/folder/target.txt",
        _credential_auth("fallback"),
        source_auth=_credential_auth("source"),
        destination_auth=_credential_auth("destination"),
    )

    assert response.ok is True
    download_auth = src_provider.download_item.call_args.args[1]
    upload_auth = dst_provider.upload_item.call_args.kwargs["auth"]
    delete_auth = src_provider.delete_item.call_args.args[1]
    assert download_auth is delete_auth
    assert upload_auth is not download_auth
    assert download_auth.username == "source-user"
    assert delete_auth.username == "source-user"
    assert upload_auth.username == "destination-user"


def test_rename_path_cross_provider_does_not_delete_when_upload_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("alfresco")
    dst_provider = DummyProvider("edocat")
    src_provider.download_item.return_value = OperationResult(
        success=True,
        operation="download",
        provider="alfresco",
        content_base64="Y29udGVudA==",
        size=7,
    )
    dst_provider.upload_item.return_value = OperationResult(
        success=False,
        operation="upload",
        provider="edocat",
        message="upload rejected",
    )

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (src_provider, type("P", (), {"path": "/source.txt"})())
        if path == "alfresco:/source.txt"
        else (dst_provider, type("P", (), {"path": "/folder/target.txt"})()),
    )

    response = bridge_service_module.rename_path("alfresco:/source.txt", "edocat:/folder/target.txt", _auth())

    assert response.ok is False
    assert "upload rejected" in (response.message or "")
    src_provider.delete_item.assert_not_called()


def test_copy_path_cross_provider_returns_failure_when_upload_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    src_provider = DummyProvider("edocat")
    dst_provider = DummyProvider("alfresco")
    src_provider.download_item.return_value = OperationResult(
        success=True,
        operation="download",
        provider="edocat",
        content_base64="dGVzdA==",
        size=4,
    )
    dst_provider.upload_item.return_value = OperationResult(
        success=False,
        operation="upload",
        provider="alfresco",
        message="upload rejected",
    )

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (src_provider, type("P", (), {"path": "/source.txt"})())
        if path == "edocat:/source.txt"
        else (dst_provider, type("P", (), {"path": "/target.txt"})()),
    )

    response = bridge_service_module.copy_path("edocat:/source.txt", "alfresco:/target.txt", _auth())

    assert response.ok is False
    assert "upload rejected" in (response.message or "")


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


def test_upload_path_rejects_large_inline_payload_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DummyProvider("edocat")

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(bridge_service_module, "_resolve", lambda destination: (provider, type("P", (), {"path": "/A/B/C"})()))

    large_inline_base64 = "A" * (6 * 1024 * 1024)
    response = bridge_service_module.upload_path(
        "edocat:/A/B/C",
        "test.txt",
        _auth(),
        content_base64=large_inline_base64,
        overwrite=False,
    )

    assert response.ok is False
    assert "inline content_base64" in (response.message or "")
    assert "upload-raw" in (response.message or "")
    provider.make_dir.assert_not_called()
    provider.upload_item.assert_not_called()


def test_upload_path_source_path_bypasses_base64_limit(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    provider = DummyProvider("edocat", config={"transfer": {"maxBase64Bytes": 3}})
    provider.upload_item.return_value = OperationResult(success=True, operation="upload", provider="edocat")

    source = tmp_path / "large.bin"
    source.write_bytes(b"12345")

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(bridge_service_module, "_resolve", lambda destination: (provider, type("P", (), {"path": "/A/B/C"})()))

    response = bridge_service_module.upload_path(
        "edocat:/A/B/C",
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


def test_stat_path_deduplicates_repeated_leaf(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DummyProvider("alfresco")
    valid_item = DmsItem(
        id="f-1",
        name="Plant 3D Models_25_06_27.zip",
        path="/A/B/Plant 3D Models_25_06_27.zip",
        is_folder=False,
    )

    def _stat_side_effect(path: str, auth: BridgeAuthContext):
        if path == "/A/B/Plant 3D Models_25_06_27.zip/Plant 3D Models_25_06_27.zip":
            return None
        if path == "/A/B/Plant 3D Models_25_06_27.zip":
            return valid_item
        return None

    provider.stat_item.side_effect = _stat_side_effect

    monkeypatch.setattr(bridge_service_module, "validate_bridge_auth", lambda auth: None)
    monkeypatch.setattr(
        bridge_service_module,
        "_resolve",
        lambda path: (
            provider,
            type(
                "P",
                (),
                {"path": "/A/B/Plant 3D Models_25_06_27.zip/Plant 3D Models_25_06_27.zip"},
            )(),
        ),
    )

    response = bridge_service_module.stat_path(
        "alfresco:/A/B/Plant 3D Models_25_06_27.zip/Plant 3D Models_25_06_27.zip",
        _auth(),
    )

    assert response.ok is True
    assert response.data is not None
    assert response.data["path"] == "/A/B/Plant 3D Models_25_06_27.zip"
    assert provider.stat_item.call_args_list[0].args[0] == "/A/B/Plant 3D Models_25_06_27.zip/Plant 3D Models_25_06_27.zip"
    assert provider.stat_item.call_args_list[1].args[0] == "/A/B/Plant 3D Models_25_06_27.zip"

