from __future__ import annotations

from edocat_bridge.models.operation import OperationResult
from edocat_bridge.services.provider_service import get_provider


def copy_item(source: str, destination: str, provider_name: str | None = None) -> OperationResult:
    provider = get_provider(provider_name)
    return provider.copy_item(source, destination)
