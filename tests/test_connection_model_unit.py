from __future__ import annotations

import pytest

from dms_provider_bridge.models.connection import ConnectionConfig
from dms_provider_bridge.models.provider import ProviderConfig


pytestmark = pytest.mark.unit


def test_provider_config_is_connection_config_alias() -> None:
    assert ProviderConfig is ConnectionConfig

    config = ProviderConfig(name="alfresco")

    assert config.name == "alfresco"
    assert config.enabled is True
    assert config.endpoint is None
