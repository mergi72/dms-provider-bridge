from __future__ import annotations

from dms_provider_bridge.adapters.commander_api import parse_wfx_path
from dms_provider_bridge.models.operation import OperationResult
from dms_provider_bridge.services.provider_service import get_provider


def _split_wfx_path(path: str) -> tuple[str | None, str]:
    raw = path.strip()
    if not raw:
        return None, raw
    prefix, sep, suffix = raw.partition(":")
    if sep and len(prefix.strip()) > 1 and suffix.strip().replace("\\", "/").startswith("/"):
        parsed = parse_wfx_path(raw)
        return parsed.provider, parsed.path
    return None, raw


def _effective_provider(explicit_provider: str | None, source_provider: str | None) -> str | None:
    if explicit_provider and source_provider and explicit_provider.strip().lower().rstrip(":") != source_provider:
        raise ValueError(
            f"Provider mismatch: explicit provider '{explicit_provider}' does not match path provider '{source_provider}'."
        )
    return explicit_provider or source_provider


def rename_item(source: str, destination: str, provider_name: str | None = None) -> OperationResult:
    source_provider, source_path = _split_wfx_path(source)
    destination_provider, destination_path = _split_wfx_path(destination)
    effective_provider = _effective_provider(provider_name, source_provider)
    if source_provider and destination_provider and source_provider != destination_provider:
        raise ValueError("Cross-provider rename is not supported.")
    if source_provider and destination_provider is None:
        raise ValueError("Destination path provider is missing.")
    if destination_provider and source_provider is None:
        raise ValueError("Source path provider is missing.")

    provider = get_provider(effective_provider)
    return provider.rename_item(source_path, destination_path)


def delete_item(target: str, provider_name: str | None = None) -> OperationResult:
    target_provider, target_path = _split_wfx_path(target)
    effective_provider = _effective_provider(provider_name, target_provider)
    provider = get_provider(effective_provider)
    return provider.delete_item(target_path)

