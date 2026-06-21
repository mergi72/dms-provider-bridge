"""Deprecated provider-named runtime service alias.

Runtime connection discovery now lives in
``dms_provider_bridge.services.connection_runtime_service``. This module remains
temporarily for older imports and tests that still use provider-era naming.
Prefer importing from ``connection_runtime_service`` in new code.
"""

from __future__ import annotations

from dms_provider_bridge.services.connection_runtime_service import *  # noqa: F401,F403

