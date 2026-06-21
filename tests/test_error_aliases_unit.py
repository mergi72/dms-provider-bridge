from __future__ import annotations

import pytest

from dms_provider_bridge.adapters.commander_api import WfxErrorCode
from dms_provider_bridge.core.errors import ConnectionOperationError, ProviderOperationError
from dms_provider_bridge.services.bridge_errors import map_exception


pytestmark = pytest.mark.unit


def test_provider_operation_error_is_legacy_alias_for_connection_operation_error() -> None:
    assert ProviderOperationError is ConnectionOperationError


def test_connection_operation_error_maps_to_wfx_internal_error() -> None:
    mapped = map_exception(ConnectionOperationError("copy failed", status_code=507))

    assert mapped.code == WfxErrorCode.INTERNAL_ERROR
    assert mapped.message == "copy failed"
    assert mapped.metadata == {"upstream_status_code": 507}
