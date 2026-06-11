from __future__ import annotations

import pytest

import dms_provider_bridge.services.listing_service as listing_service_module
import dms_provider_bridge.services.provider_service as provider_service_module
from dms_provider_bridge.core.errors import ConfigurationError


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


def test_list_registered_providers_contains_known() -> None:
    providers = provider_service_module.list_registered_providers()

    assert set(providers) >= {"edocat", "alfresco"}


def test_list_registered_providers_uses_configured_machine_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_service_module, "list_provider_config_names", lambda: ["alfresco", "unknown"])

    providers = provider_service_module.list_registered_providers()

    assert providers == ["alfresco"]


def test_get_default_provider_name_uses_env_when_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_service_module, "load_config", lambda: {})
    monkeypatch.setenv("DMS_PROVIDER_DEFAULT_PROVIDER", "alfresco")

    default_provider = provider_service_module.get_default_provider_name()

    assert default_provider == "alfresco"


def test_get_default_provider_name_requires_configured_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_service_module, "load_config", lambda: {})
    monkeypatch.setenv("DMS_PROVIDER_DEFAULT_PROVIDER", "unknown")

    with pytest.raises(ConfigurationError):
        provider_service_module.get_default_provider_name()


def test_get_default_provider_name_uses_config_when_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_service_module, "load_config", lambda: {"provider": {"default": "alfresco"}})
    monkeypatch.setenv("DMS_PROVIDER_DEFAULT_PROVIDER", "edocat")

    default_provider = provider_service_module.get_default_provider_name()

    assert default_provider == "alfresco"


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
