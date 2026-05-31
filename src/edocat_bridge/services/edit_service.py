from __future__ import annotations

from edocat_bridge.models.operation import OperationResult
from edocat_bridge.services.provider_service import get_provider


def rename_item(source: str, destination: str, provider_name: str | None = None) -> OperationResult:
    provider = get_provider(provider_name)
    return provider.rename_item(source, destination)


def delete_item(target: str, provider_name: str | None = None) -> OperationResult:
    provider = get_provider(provider_name)
    return provider.delete_item(target)
