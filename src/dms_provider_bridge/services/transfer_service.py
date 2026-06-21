from __future__ import annotations

from dms_provider_bridge.adapters.commander_api import split_optional_wfx_path
from dms_provider_bridge.models.operation import OperationResult
from dms_provider_bridge.core.connection_aliases import resolve_connection_alias, resolve_path_connection
from dms_provider_bridge.services.connection_runtime_service import get_connection_runtime


def copy_connection_item(
    source: str,
    destination: str,
    connection_name: str | None = None,
) -> OperationResult:
    source_connection, source_path = split_optional_wfx_path(source)
    destination_connection, destination_path = split_optional_wfx_path(destination)
    effective_connection = resolve_path_connection(connection_name, source_connection)
    if source_connection and destination_connection and source_connection != destination_connection:
        raise ValueError("Cross-connection copy is not supported.")
    if source_connection and destination_connection is None:
        raise ValueError("Destination path connection is missing.")
    if destination_connection and source_connection is None:
        raise ValueError("Source path connection is missing.")

    connection_runtime = get_connection_runtime(effective_connection)
    return connection_runtime.copy_item(source_path, destination_path)


def copy_item(
    source: str,
    destination: str,
    provider_name: str | None = None,
    *,
    connection_name: str | None = None,
) -> OperationResult:
    return copy_connection_item(source, destination, resolve_connection_alias(provider_name, connection_name))

