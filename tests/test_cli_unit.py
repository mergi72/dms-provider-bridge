from __future__ import annotations

from types import SimpleNamespace

import pytest

from dms_provider_bridge.adapters import cli as cli_module


pytestmark = pytest.mark.unit


def test_cli_uses_connection_argument(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    calls = []

    def fake_list_connection_items(path: str, connection_name: str | None = None):
        calls.append((path, connection_name))
        return SimpleNamespace(model_dump_json=lambda indent=2: '{"ok": true}')

    monkeypatch.setattr(cli_module, "list_connection_items", fake_list_connection_items)
    monkeypatch.setattr("sys.argv", ["dms-provider-bridge", "/contracts", "--connection", "alfresco"])

    cli_module.run_cli()

    assert calls == [("/contracts", "alfresco")]
    assert capsys.readouterr().out.strip() == '{"ok": true}'


def test_cli_keeps_provider_argument_as_legacy_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_list_connection_items(path: str, connection_name: str | None = None):
        calls.append((path, connection_name))
        return SimpleNamespace(model_dump_json=lambda indent=2: "{}")

    monkeypatch.setattr(cli_module, "list_connection_items", fake_list_connection_items)
    monkeypatch.setattr("sys.argv", ["dms-provider-bridge", "/contracts", "--provider", "alfresco"])

    cli_module.run_cli()

    assert calls == [("/contracts", "alfresco")]


def test_cli_rejects_connection_provider_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["dms-provider-bridge", "/contracts", "--connection", "alfresco", "--provider", "edocat"],
    )

    with pytest.raises(SystemExit):
        cli_module.run_cli()
