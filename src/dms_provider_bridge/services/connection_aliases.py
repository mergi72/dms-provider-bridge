from __future__ import annotations


def normalize_connection_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower().rstrip(":")
    return normalized or None


def resolve_connection_alias(
    legacy_provider_alias: str | None = None,
    connection_name: str | None = None,
    *,
    connection_driver_name_fn=None,
) -> str | None:
    legacy = normalize_connection_name(legacy_provider_alias)
    connection = normalize_connection_name(connection_name)
    if legacy and connection and legacy != connection:
        if connection_driver_name_fn is None or connection_driver_name_fn(connection) != legacy:
            raise ValueError(
                f"Connection mismatch: provider_name '{legacy_provider_alias}' does not match "
                f"connection_name '{connection_name}'."
            )
    return connection or legacy


def resolve_path_connection(explicit_connection: str | None, path_connection: str | None) -> str | None:
    explicit = normalize_connection_name(explicit_connection)
    parsed = normalize_connection_name(path_connection)
    if explicit and parsed and explicit != parsed:
        raise ValueError(
            f"Connection mismatch: explicit connection '{explicit_connection}' does not match "
            f"path connection '{path_connection}'."
        )
    return explicit or parsed
