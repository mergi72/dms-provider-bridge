from __future__ import annotations

from dms_provider_bridge.adapters.commander_api import split_optional_wfx_path
from dms_provider_bridge.models.operation import OperationResult
from dms_provider_bridge.services.provider_service import get_connection_runtime


def _effective_connection(explicit_connection: str | None, source_connection: str | None) -> str | None:
    if explicit_connection and source_connection and explicit_connection.strip().lower().rstrip(":") != source_connection:
        raise ValueError(
            f"Connection mismatch: explicit connection '{explicit_connection}' does not match path connection '{source_connection}'."
        )
    return explicit_connection or source_connection


def rename_item(source: str, destination: str, provider_name: str | None = None) -> OperationResult:
    source_connection, source_path = split_optional_wfx_path(source)
    destination_connection, destination_path = split_optional_wfx_path(destination)
    effective_connection = _effective_connection(provider_name, source_connection)
    if source_connection and destination_connection and source_connection != destination_connection:
        raise ValueError("Cross-connection rename is not supported.")
    if source_connection and destination_connection is None:
        raise ValueError("Destination path connection is missing.")
    if destination_connection and source_connection is None:
        raise ValueError("Source path connection is missing.")

    provider = get_connection_runtime(effective_connection)
    return provider.rename_item(source_path, destination_path)


def delete_item(target: str, provider_name: str | None = None) -> OperationResult:
    target_connection, target_path = split_optional_wfx_path(target)
    effective_connection = _effective_connection(provider_name, target_connection)
    provider = get_connection_runtime(effective_connection)
    return provider.delete_item(target_path)

