from __future__ import annotations

from dms_provider_bridge.models.connection import ConnectionConfig


# Deprecated compatibility alias. New code should use ConnectionConfig; the
# provider name used to mean the user-visible TC mount, which is now connection.
ProviderConfig = ConnectionConfig
