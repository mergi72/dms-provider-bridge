from __future__ import annotations

import pytest

from dms_provider_bridge.models.listing import ListingResult
from dms_provider_bridge.models.operation import OperationResult
from dms_provider_bridge.models.bridge import WfxResponse
from dms_provider_bridge.models.item import DmsItem
from dms_provider_bridge.models.search import select_unique_items


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


def test_search_selection_defaults_to_unique_files() -> None:
    items = [
        DmsItem(id="folder", name="docs", path="/docs", is_folder=True),
        DmsItem(id="doc-1", name="first.docx", path="/docs/first.docx"),
        DmsItem(id="doc-1", name="duplicate.docx", path="/elsewhere/duplicate.docx"),
        DmsItem(id="doc-2", name="second.pdf", path="/docs/second.pdf"),
    ]

    selected = select_unique_items(items, max_results=20, files_only=True)

    assert [item.id for item in selected] == ["doc-1", "doc-2"]


def test_search_selection_can_include_folders() -> None:
    items = [DmsItem(id="folder", name="docs", path="/docs", is_folder=True)]

    assert select_unique_items(items, max_results=20, files_only=False) == items


def test_search_selection_uses_path_when_stable_id_is_blank() -> None:
    items = [
        DmsItem(id=" ", name="first.txt", path="/A/first.txt"),
        DmsItem(id="", name="duplicate.txt", path="/a/FIRST.txt"),
        DmsItem(id="", name="second.txt", path="/a/second.txt"),
    ]

    selected = select_unique_items(items, max_results=20, files_only=True)

    assert [item.name for item in selected] == ["first.txt", "second.txt"]
