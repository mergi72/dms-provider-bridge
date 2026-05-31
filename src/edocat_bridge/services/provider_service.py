from __future__ import annotations

import os

from edocat_bridge.core.errors import ProviderNotFoundError
from edocat_bridge.providers.alfresco import AlfrescoProvider
from edocat_bridge.providers.base import Provider
from edocat_bridge.providers.edocat import EdocatProvider
from edocat_bridge.providers.fso import FsoProvider


_PROVIDER_REGISTRY: dict[str, Provider] = {
    "edocat": EdocatProvider(),
    "alfresco": AlfrescoProvider(),
    "fso": FsoProvider(),
}


def get_provider(provider_name: str | None = None) -> Provider:
    name = provider_name or os.getenv("EDOCAT_PROVIDER") or "edocat"
    provider = _PROVIDER_REGISTRY.get(name)
    if provider is None:
        raise ProviderNotFoundError(f"Provider '{name}' is not registered.")
    return provider
