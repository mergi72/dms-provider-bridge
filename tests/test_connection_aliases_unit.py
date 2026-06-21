from __future__ import annotations

import pytest

from dms_provider_bridge.services.connection_aliases import (
    normalize_connection_name,
    resolve_connection_alias,
    resolve_path_connection,
)


pytestmark = pytest.mark.unit


def test_normalize_connection_name_strips_colon_and_case() -> None:
    assert normalize_connection_name(" Alfresco1: ") == "alfresco1"
    assert normalize_connection_name("") is None
    assert normalize_connection_name(None) is None


def test_resolve_connection_alias_prefers_explicit_connection() -> None:
    assert resolve_connection_alias("alfresco", "alfresco") == "alfresco"
    assert resolve_connection_alias(None, "alfresco") == "alfresco"
    assert resolve_connection_alias("alfresco", None) == "alfresco"


def test_resolve_connection_alias_rejects_mismatch() -> None:
    with pytest.raises(ValueError, match="Connection mismatch"):
        resolve_connection_alias("alfresco", "edocat")


def test_resolve_connection_alias_accepts_driver_alias_when_resolver_allows_it() -> None:
    assert (
        resolve_connection_alias(
            "webdav",
            "webdav1",
            connection_driver_name_fn=lambda connection_name: "webdav" if connection_name == "webdav1" else None,
        )
        == "webdav1"
    )


def test_resolve_path_connection_rejects_mismatch() -> None:
    with pytest.raises(ValueError, match="Connection mismatch"):
        resolve_path_connection("alfresco", "edocat")
