from __future__ import annotations

from dms_provider_bridge.adapters.commander_api import split_optional_wfx_path
from dms_provider_bridge.models.operation import OperationResult
from dms_provider_bridge.services.provider_service import get_connection_runtime


def _normalize_connection(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().rstrip(":")
    return normalized or None


def _effective_connection(explicit_connection: str | None, source_connection: str | None) -> str | None:
    explicit = _normalize_connection(explicit_connection)
    source = _normalize_connection(source_connection)
    if explicit and source and explicit != source:
        raise ValueError(
            f"Connection mismatch: explicit connection '{explicit_connection}' does not match path connection '{source_connection}'."
        )
    return explicit or source


def _requested_connection(legacy_provider_name: str | None = None, connection_name: str | None = None) -> str | None:
    legacy = _normalize_connection(legacy_provider_name)
    connection = _normalize_connection(connection_name)
    if legacy and connection and legacy != connection:
        raise ValueError(
            f"Connection mismatch: provider_name '{legacy_provider_name}' does not match connection_name '{connection_name}'."
        )
    return connection or legacy


def rename_connection_item(
    source: str,
    destination: str,
    connection_name: str | None = None,
) -> OperationResult:
    source_connection, source_path = split_optional_wfx_path(source)
    destination_connection, destination_path = split_optional_wfx_path(destination)
    effective_connection = _effective_connection(connection_name, source_connection)
    if source_connection and destination_connection and source_connection != destination_connection:
        raise ValueError("Cross-connection rename is not supported.")
    if source_connection and destination_connection is None:
        raise ValueError("Destination path connection is missing.")
    if destination_connection and source_connection is None:
        raise ValueError("Source path connection is missing.")

    provider = get_connection_runtime(effective_connection)
    return provider.rename_item(source_path, destination_path)


def rename_item(
    source: str,
    destination: str,
    provider_name: str | None = None,
    *,
    connection_name: str | None = None,
) -> OperationResult:
    return rename_connection_item(source, destination, _requested_connection(provider_name, connection_name))


def delete_connection_item(target: str, connection_name: str | None = None) -> OperationResult:
    target_connection, target_path = split_optional_wfx_path(target)
    effective_connection = _effective_connection(connection_name, target_connection)
    provider = get_connection_runtime(effective_connection)
    return provider.delete_item(target_path)


def delete_item(target: str, provider_name: str | None = None, *, connection_name: str | None = None) -> OperationResult:
    return delete_connection_item(target, _requested_connection(provider_name, connection_name))

