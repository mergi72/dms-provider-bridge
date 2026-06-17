from __future__ import annotations

import pytest

from dms_provider_bridge.adapters.commander_api import build_wfx_path, map_commander_payload, parse_wfx_path, split_optional_wfx_path


pytestmark = pytest.mark.unit


def test_parse_wfx_path_normalizes_provider_and_path() -> None:
    parsed = parse_wfx_path("AlFrEsCo:contracts/sample.txt")
    assert parsed.connection == "alfresco"
    assert parsed.provider == "alfresco"
    assert parsed.path == "/contracts/sample.txt"


def test_parse_wfx_path_rejects_invalid_input() -> None:
    with pytest.raises(ValueError):
        parse_wfx_path("invalid")


def test_build_wfx_path_always_has_slash() -> None:
    assert build_wfx_path("edocat", "folder/a.txt") == "edocat:/folder/a.txt"
    assert build_wfx_path("edocat", "/folder/a.txt") == "edocat:/folder/a.txt"


def test_split_optional_wfx_path_accepts_provider_and_plain_paths() -> None:
    assert split_optional_wfx_path("alfresco:/folder/a.txt") == ("alfresco", "/folder/a.txt")
    assert split_optional_wfx_path("C:\\Users\\tester\\a.txt") == (None, "C:\\Users\\tester\\a.txt")
    assert split_optional_wfx_path("plain/path.txt") == (None, "plain/path.txt")


def test_map_commander_payload_is_passthrough() -> None:
    payload = {"x": 1, "nested": {"y": 2}}
    assert map_commander_payload(payload) == payload

