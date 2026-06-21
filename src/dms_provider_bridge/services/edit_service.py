from __future__ import annotations

from dms_provider_bridge.adapters.commander_api import split_optional_wfx_path
from dms_provider_bridge.models.operation import OperationResult
from dms_provider_bridge.core.connection_aliases import resolve_connection_alias, resolve_path_connection
from dms_provider_bridge.services.connection_runtime_service import get_connection_runtime


def rename_connection_item(
    source: str,
    destination: str,
    connection_name: str | None = None,
) -> OperationResult:
    source_connection, source_path = split_optional_wfx_path(source)
    destination_connection, destination_path = split_optional_wfx_path(destination)
    effective_connection = resolve_path_connection(connection_name, source_connection)
    if source_connection and destination_connection and source_connection != destination_connection:
        raise ValueError("Cross-connection rename is not supported.")
    if source_connection and destination_connection is None:
        raise ValueError("Destination path connection is missing.")
    if destination_connection and source_connection is None:
        raise ValueError("Source path connection is missing.")

    connection_runtime = get_connection_runtime(effective_connection)
    return connection_runtime.rename_item(source_path, destination_path)


def rename_item(
    source: str,
    destination: str,
    provider_name: str | None = None,
    *,
    connection_name: str | None = None,
) -> OperationResult:
    return rename_connection_item(source, destination, resolve_connection_alias(provider_name, connection_name))


def delete_connection_item(target: str, connection_name: str | None = None) -> OperationResult:
    target_connection, target_path = split_optional_wfx_path(target)
    effective_connection = resolve_path_connection(connection_name, target_connection)
    connection_runtime = get_connection_runtime(effective_connection)
    return connection_runtime.delete_item(target_path)


def delete_item(target: str, provider_name: str | None = None, *, connection_name: str | None = None) -> OperationResult:
    return delete_connection_item(target, resolve_connection_alias(provider_name, connection_name))

