from __future__ import annotations

from unittest.mock import Mock

import pytest

import edocat_bridge.services.edit_service as edit_service_module


pytestmark = pytest.mark.unit


class DummyProvider:
    def __init__(self) -> None:
        self.rename_item = Mock(return_value={"ok": True})
        self.delete_item = Mock(return_value={"ok": True})


def test_rename_item_parses_wfx_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DummyProvider()
    monkeypatch.setattr(edit_service_module, "get_provider", lambda provider_name=None: provider)

    edit_service_module.rename_item(
        "edocat:/folder/Upload",
        "edocat:/folder/Upload_101",
        provider_name=None,
    )

    provider.rename_item.assert_called_once_with("/folder/Upload", "/folder/Upload_101")


def test_rename_item_rejects_provider_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DummyProvider()
    monkeypatch.setattr(edit_service_module, "get_provider", lambda provider_name=None: provider)

    with pytest.raises(ValueError, match="Provider mismatch"):
        edit_service_module.rename_item(
            "edocat:/folder/Upload",
            "edocat:/folder/Upload_101",
            provider_name="alfresco",
        )


def test_delete_item_parses_wfx_path(monkeypatch: pytest.MonkeyPatch) -> None:
    provider = DummyProvider()
    monkeypatch.setattr(edit_service_module, "get_provider", lambda provider_name=None: provider)

    edit_service_module.delete_item("edocat:/folder/Upload")

    provider.delete_item.assert_called_once_with("/folder/Upload")
