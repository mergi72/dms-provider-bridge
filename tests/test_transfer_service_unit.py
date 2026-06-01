from __future__ import annotations

from unittest.mock import Mock

import pytest

import edocat_bridge.services.transfer_service as transfer_service_module


pytestmark = pytest.mark.unit


class DummyProvider:
    def __init__(self) -> None:
        self.copy_item = Mock(return_value={"ok": True})


def test_copy_item_parses_wfx_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DummyProvider()
    monkeypatch.setattr(transfer_service_module, "get_provider", lambda provider_name=None: provider)

    transfer_service_module.copy_item(
        "edocat:/folder/source.txt",
        "edocat:/folder/copied.txt",
        provider_name=None,
    )

    provider.copy_item.assert_called_once_with("/folder/source.txt", "/folder/copied.txt")


def test_copy_item_rejects_provider_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DummyProvider()
    monkeypatch.setattr(transfer_service_module, "get_provider", lambda provider_name=None: provider)

    with pytest.raises(ValueError, match="Provider mismatch"):
        transfer_service_module.copy_item(
            "edocat:/folder/source.txt",
            "edocat:/folder/copied.txt",
            provider_name="alfresco",
        )