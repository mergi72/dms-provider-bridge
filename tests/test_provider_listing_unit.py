from __future__ import annotations

import pytest

import edocat_bridge.services.listing_service as listing_service_module
import edocat_bridge.services.provider_service as provider_service_module


pytestmark = pytest.mark.unit


class _DummyProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def list_items(self, path: str):
        self.calls.append(path)
        return {"path": path}


def test_get_provider_accepts_trailing_colon() -> None:
    provider = provider_service_module.get_provider("edocat:")
    assert provider.name == "edocat"


def test_listing_service_parses_wfx_path_when_provider_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy = _DummyProvider()

    def fake_get_provider(name: str | None = None):
        assert name == "edocat"
        return dummy

    monkeypatch.setattr(listing_service_module, "get_provider", fake_get_provider)

    result = listing_service_module.list_items("edocat:/contracts")

    assert dummy.calls == ["/contracts"]
    assert result == {"path": "/contracts"}


def test_listing_service_keeps_explicit_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy = _DummyProvider()

    def fake_get_provider(name: str | None = None):
        assert name == "alfresco"
        return dummy

    monkeypatch.setattr(listing_service_module, "get_provider", fake_get_provider)

    result = listing_service_module.list_items("/contracts", provider_name="alfresco")

    assert dummy.calls == ["/contracts"]
    assert result == {"path": "/contracts"}