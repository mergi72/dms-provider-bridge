from __future__ import annotations

import pytest

from dms_provider_bridge.services.bridge_transfer_ops import (
    max_cross_connection_upload_bytes,
    max_cross_provider_upload_bytes,
    max_inline_upload_bytes,
)


pytestmark = pytest.mark.unit


class DummyConnectionRuntime:
    def __init__(self, config: dict) -> None:
        self.config = config


def test_cross_connection_upload_limit_uses_connection_runtime_config() -> None:
    runtime = DummyConnectionRuntime({"transfer": {"maxBase64Bytes": 1234}})

    assert max_cross_connection_upload_bytes(runtime) == 1234
    assert max_cross_provider_upload_bytes(runtime) == 1234


def test_inline_upload_limit_is_capped_by_cross_connection_limit() -> None:
    runtime = DummyConnectionRuntime(
        {
            "transfer": {"maxBase64Bytes": 512},
            "upload": {"inline": {"maxBytes": 2048}},
        }
    )

    assert max_inline_upload_bytes(runtime) == 512
