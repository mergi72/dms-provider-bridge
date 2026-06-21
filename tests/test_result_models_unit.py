from __future__ import annotations

import pytest

from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.models.operation import OperationResult


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


def test_operation_result_exposes_connection_alias_for_legacy_provider() -> None:
    result = OperationResult(success=True, operation="upload", provider="webdav")

    assert result.provider == "webdav"
    assert result.connection == "webdav"
    assert result.model_dump()["connection"] == "webdav"


def test_operation_result_preserves_explicit_connection() -> None:
    result = OperationResult(success=True, operation="upload", provider="webdav", connection="webdav1")

    assert result.provider == "webdav"
    assert result.connection == "webdav1"
