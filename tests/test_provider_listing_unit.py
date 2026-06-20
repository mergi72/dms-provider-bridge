from __future__ import annotations

import pytest
import pkgutil

import dms_provider_bridge.drivers as drivers_package
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


def test_drivers_package_exposes_current_driver_modules() -> None:
    module_names = {module.name for module in pkgutil.iter_modules(drivers_package.__path__)}

    assert {"alfresco", "edocat", "base"} <= module_names


def test_get_connection_runtime_accepts_trailing_colon() -> None:
    connection = provider_service_module.get_connection_runtime("edocat:")
    assert connection.name == "edocat"


def test_list_registered_connections_contains_known() -> None:
    connections = provider_service_module.list_registered_connections()

    assert set(connections) >= {"edocat", "alfresco"}


def test_runtime_registry_snapshot_maps_wfx_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_service_module, "_DRIVER_FACTORIES", {"alfresco": _DummyProvider, "edocat": _DummyProvider})
    monkeypatch.setattr(provider_service_module, "list_connection_config_names", lambda: ["alfresco", "edocat"])
    monkeypatch.setattr(provider_service_module, "connection_driver_name", lambda name: name)
    monkeypatch.setattr(
        provider_service_module,
        "load_connection_metadata",
        lambda name: {"name": name, "driver": name, "mount": f"{name}:/", "display_name": name, "description": None},
    )

    snapshot = provider_service_module.runtime_registry_snapshot()
    connections = {item["name"]: item for item in snapshot["connections"]}

    assert snapshot["provider_abc"] == "provider"
    assert set(snapshot["wfx_connections"]) >= {"edocat", "alfresco"}
    assert set(snapshot["available_drivers"]) >= {"edocat", "alfresco"}
    assert connections["alfresco"]["driver"] == "alfresco"
    assert connections["alfresco"]["mount"] == "alfresco:/"
    provider_service_module.reload_provider_cache()


def test_list_registered_connections_uses_configured_machine_drivers_when_connections_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_service_module, "list_connection_config_names", lambda: [])
    monkeypatch.setattr(provider_service_module, "list_provider_config_names", lambda: ["alfresco", "unknown"])

    connections = provider_service_module.list_registered_connections()

    assert connections == ["alfresco"]


def test_list_registered_connections_wraps_connection_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_service_module, "list_connection_config_names", lambda: ["company"])
    monkeypatch.setattr(provider_service_module, "connection_driver_name", lambda name: "alfresco" if name == "company" else None)

    assert provider_service_module.list_registered_connections() == ["company"]


def test_reload_provider_cache_clears_cached_instances(monkeypatch: pytest.MonkeyPatch) -> None:
    provider_service_module.reload_provider_cache()
    monkeypatch.setattr(provider_service_module, "_DRIVER_FACTORIES", {"dummy": _DummyProvider})
    monkeypatch.setattr(provider_service_module, "list_connection_config_names", lambda: [])
    monkeypatch.setattr(provider_service_module, "list_provider_config_names", lambda: ["dummy"])

    first = provider_service_module.get_connection_runtime("dummy")
    second = provider_service_module.get_connection_runtime("dummy")
    provider_service_module.reload_provider_cache()
    third = provider_service_module.get_connection_runtime("dummy")

    assert first is second
    assert third is not first
    provider_service_module.reload_provider_cache()


def test_driver_factories_use_current_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    factories = {"dummy": _DummyProvider}
    monkeypatch.setattr(provider_service_module, "_DRIVER_FACTORIES", factories)

    assert provider_service_module._driver_factories() is factories


def test_get_default_connection_name_uses_env_when_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_service_module, "load_config", lambda: {})
    monkeypatch.setattr(provider_service_module, "list_connection_config_names", lambda: [])
    monkeypatch.setenv("DMS_PROVIDER_DEFAULT_CONNECTION", "alfresco")

    default_connection = provider_service_module.get_default_connection_name()

    assert default_connection == "alfresco"


def test_get_default_connection_name_requires_configured_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_service_module, "load_config", lambda: {})
    monkeypatch.setattr(provider_service_module, "list_connection_config_names", lambda: [])
    monkeypatch.setenv("DMS_PROVIDER_DEFAULT_CONNECTION", "unknown")

    with pytest.raises(ConfigurationError):
        provider_service_module.get_default_connection_name()


def test_get_default_connection_name_uses_config_when_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_service_module, "load_config", lambda: {"connection": {"default": "alfresco"}})
    monkeypatch.setattr(provider_service_module, "list_connection_config_names", lambda: [])
    monkeypatch.setenv("DMS_PROVIDER_DEFAULT_CONNECTION", "edocat")

    default_connection = provider_service_module.get_default_connection_name()

    assert default_connection == "alfresco"


def test_list_registered_connections_prefers_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(provider_service_module, "list_connection_config_names", lambda: ["company", "unknown"])
    monkeypatch.setattr(provider_service_module, "connection_driver_name", lambda name: {"company": "alfresco"}.get(name))

    connections = provider_service_module.list_registered_connections()

    assert connections == ["company"]


def test_get_connection_runtime_instantiates_connection_driver(monkeypatch: pytest.MonkeyPatch) -> None:
    provider_service_module.reload_provider_cache()

    class DummyProvider:
        name = "dummy"

        def __init__(self, name=None, config=None) -> None:
            self.name = name
            self.config = config

    monkeypatch.setattr(provider_service_module, "_DRIVER_FACTORIES", {"dummy": DummyProvider})
    monkeypatch.setattr(provider_service_module, "list_connection_config_names", lambda: ["mount1"])
    monkeypatch.setattr(provider_service_module, "connection_driver_name", lambda name: "dummy" if name == "mount1" else None)
    monkeypatch.setattr(provider_service_module, "load_connection_config", lambda name: {"driver": "dummy", "base_url": "x"})

    provider = provider_service_module.get_connection_runtime("mount1")

    assert provider.name == "mount1"
    assert provider.config == {"driver": "dummy", "base_url": "x"}
    provider_service_module.reload_provider_cache()


def test_get_connection_runtime_aliases_connection_driver_config(monkeypatch: pytest.MonkeyPatch) -> None:
    provider_service_module.reload_provider_cache()

    class DummyProvider:
        name = "dummy"

        def __init__(self, name=None, config=None) -> None:
            self.name = name
            self.config = config

    monkeypatch.setattr(provider_service_module, "_DRIVER_FACTORIES", {"dummy": DummyProvider})
    monkeypatch.setattr(provider_service_module, "list_connection_config_names", lambda: ["mount1"])
    monkeypatch.setattr(provider_service_module, "connection_driver_name", lambda name: "dummy" if name == "mount1" else None)
    monkeypatch.setattr(provider_service_module, "load_connection_config", lambda name: {"driver": "dummy", "base_url": "x"})

    runtime = provider_service_module.get_connection_runtime("mount1")

    assert runtime.name == "mount1"
    assert runtime.config == {"driver": "dummy", "base_url": "x"}
    provider_service_module.reload_provider_cache()


def test_listing_service_parses_wfx_path_when_provider_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy = _DummyProvider()

    def fake_get_connection_runtime(name: str | None = None):
        assert name == "edocat"
        return dummy

    monkeypatch.setattr(listing_service_module, "get_connection_runtime", fake_get_connection_runtime)

    result = listing_service_module.list_items("edocat:/contracts")

    assert dummy.calls == ["/contracts"]
    assert result == {"path": "/contracts"}


def test_listing_service_keeps_explicit_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy = _DummyProvider()

    def fake_get_connection_runtime(name: str | None = None):
        assert name == "alfresco"
        return dummy

    monkeypatch.setattr(listing_service_module, "get_connection_runtime", fake_get_connection_runtime)

    result = listing_service_module.list_items("/contracts", provider_name="alfresco")

    assert dummy.calls == ["/contracts"]
    assert result == {"path": "/contracts"}


def test_listing_service_accepts_connection_name_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy = _DummyProvider()

    def fake_get_connection_runtime(name: str | None = None):
        assert name == "alfresco"
        return dummy

    monkeypatch.setattr(listing_service_module, "get_connection_runtime", fake_get_connection_runtime)

    result = listing_service_module.list_items("/contracts", connection_name="alfresco")

    assert dummy.calls == ["/contracts"]
    assert result == {"path": "/contracts"}


def test_listing_service_accepts_driver_name_with_connection_name(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy = _DummyProvider()

    def fake_get_connection_runtime(name: str | None = None):
        assert name == "webdav1"
        return dummy

    monkeypatch.setattr(listing_service_module, "connection_driver_name", lambda name: "webdav" if name == "webdav1" else None)
    monkeypatch.setattr(listing_service_module, "get_connection_runtime", fake_get_connection_runtime)

    result = listing_service_module.list_items("/contracts", provider_name="webdav", connection_name="webdav1")

    assert dummy.calls == ["/contracts"]
    assert result == {"path": "/contracts"}


def test_listing_service_has_connection_first_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    dummy = _DummyProvider()

    def fake_get_connection_runtime(name: str | None = None):
        assert name == "alfresco"
        return dummy

    monkeypatch.setattr(listing_service_module, "get_connection_runtime", fake_get_connection_runtime)

    result = listing_service_module.list_connection_items("/contracts", connection_name="alfresco")

    assert dummy.calls == ["/contracts"]
    assert result == {"path": "/contracts"}
