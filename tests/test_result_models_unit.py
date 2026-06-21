from __future__ import annotations

import pytest

from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.models.operation import OperationResult
from dms_provider_bridge.models.bridge import WfxResponse


pytestmark = pytest.mark.unit


def test_listing_result_exposes_connection_alias_for_legacy_provider() -> None:
    result = ListingResult(provider="alfresco", path="/", total=0, items=[])

    assert result.provider == "alfresco"
    assert result.connection == "alfresco"
    assert result.model_dump()["connection"] == "alfresco"


def test_listing_result_preserves_explicit_connection() -> None:
    result = ListingResult(provider="alfresco", connection="alfresco1", path="/", total=0, items=[])

    assert result.provider == "alfresco"
    assert result.connection == "alfresco1"


def test_listing_result_accepts_connection_as_primary_name() -> None:
    result = ListingResult(connection="alfresco1", path="/", total=0, items=[])

    assert result.connection == "alfresco1"
    assert result.provider == "alfresco1"
    assert result.model_dump()["provider"] == "alfresco1"


def test_operation_result_exposes_connection_alias_for_legacy_provider() -> None:
    result = OperationResult(success=True, operation="upload", provider="webdav")

    assert result.provider == "webdav"
    assert result.connection == "webdav"
    assert result.model_dump()["connection"] == "webdav"


def test_operation_result_preserves_explicit_connection() -> None:
    result = OperationResult(success=True, operation="upload", provider="webdav", connection="webdav1")

    assert result.provider == "webdav"
    assert result.connection == "webdav1"


def test_operation_result_accepts_connection_as_primary_name() -> None:
    result = OperationResult(success=True, operation="upload", connection="webdav1")

    assert result.connection == "webdav1"
    assert result.provider == "webdav1"
    assert result.model_dump()["provider"] == "webdav1"


def test_wfx_response_mirrors_connection_aliases_in_data_payload() -> None:
    response = WfxResponse(ok=True, data={"connection": "edocat1", "path": "/"})

    assert response.data["connection"] == "edocat1"
    assert response.data["provider"] == "edocat1"
