from __future__ import annotations

import pytest

from dms_provider_bridge.drivers.alfresco import AlfrescoProvider
from dms_provider_bridge.drivers.edocat import EdocatProvider
from dms_provider_bridge.drivers.webdav import WebdavProvider
from dms_provider_bridge.providers.alfresco import AlfrescoProvider as LegacyAlfrescoProvider
from dms_provider_bridge.providers.edocat import EdocatProvider as LegacyEdocatProvider
from dms_provider_bridge.providers.webdav import WebdavProvider as LegacyWebdavProvider


pytestmark = pytest.mark.unit


def test_provider_package_keeps_legacy_driver_imports() -> None:
    assert LegacyAlfrescoProvider is AlfrescoProvider
    assert LegacyEdocatProvider is EdocatProvider
    assert LegacyWebdavProvider is WebdavProvider
