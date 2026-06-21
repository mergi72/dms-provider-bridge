"""Backward-compatible provider-named runtime service.

Runtime connection discovery now lives in
``dms_provider_bridge.services.connection_runtime_service``. This module remains
for older imports and tests that still use provider-era naming.
"""

from __future__ import annotations

from dms_provider_bridge.services.connection_runtime_service import *  # noqa: F401,F403

