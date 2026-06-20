from __future__ import annotations

# pyright: reportMissingTypeStubs=false

import pytest

import dms_provider_bridge.core.credentials as credentials_module  # type: ignore[import-untyped]
import dms_provider_bridge.services.auth_resolver as auth_resolver_module  # type: ignore[import-untyped]
import dms_provider_bridge.services.auth_service as auth_service_module  # type: ignore[import-untyped]
from dms_provider_bridge.core.credentials import ProviderCredentials  # type: ignore[import-untyped]
from dms_provider_bridge.core.errors import AuthenticationError  # type: ignore[import-untyped]
from dms_provider_bridge.models.bridge import BridgeAuthContext  # type: ignore[import-untyped]


pytestmark = pytest.mark.unit


def test_validate_bridge_auth_loads_windows_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_service_module,
        "load_windows_credential",
        lambda credential_id: ProviderCredentials(base_url="", username="vault-user", password="vault-pass"),
    )

    auth = BridgeAuthContext(mode="credentials", credential_id="edocat-prod")
    result = auth_service_module.validate_bridge_auth(auth)

    assert result.username == "vault-user"
    assert result.password == "vault-pass"


def test_validate_bridge_auth_accepts_inline_credentials() -> None:
    auth = BridgeAuthContext(mode="credentials", username="user", password="secret")

    result = auth_service_module.validate_bridge_auth(auth)

    assert result.username == "user"
    assert result.password == "secret"


def test_windows_auth_payload_maps_target_to_credential_id() -> None:
    auth = BridgeAuthContext(mode="windows", target="tc-wfx/bridge")

    assert auth.mode == "credentials"
    assert auth.credential_id == "tc-wfx/bridge"


def test_validate_bridge_auth_prefers_inline_credentials_over_credential_id(monkeypatch: pytest.MonkeyPatch) -> None:
    def _should_not_load(_credential_id: str) -> ProviderCredentials:
        raise AssertionError("inline credentials must not trigger Windows Credential Manager lookup")

    monkeypatch.setattr(auth_service_module, "load_windows_credential", _should_not_load)
    auth = BridgeAuthContext(
        mode="credentials",
        credential_id="tc-wfx/bridge",
        username="broker-user",
        password="broker-pass",
    )

    result = auth_service_module.validate_bridge_auth(auth)

    assert result.username == "broker-user"
    assert result.password == "broker-pass"


def test_validate_bridge_auth_requires_credentials_or_credential_id() -> None:
    auth = BridgeAuthContext(mode="credentials")

    with pytest.raises(AuthenticationError, match="credentials mode requires either credential_id"):
        auth_service_module.validate_bridge_auth(auth)


def test_resolve_alfresco_credentials_uses_provider_windows_target(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        credentials_module,
        "load_windows_credential",
        lambda credential_id: ProviderCredentials(base_url="", username="vault-user", password="vault-pass"),
    )

    auth = BridgeAuthContext(mode="winuser", win_user="DOMAIN\\tester")
    result = credentials_module.resolve_alfresco_credentials(
        auth,
        "https://example.test/alfresco",
        provider_config={"credentials": {"mode": "windows", "target": "alfresco-prod"}},
    )

    assert result.username == "vault-user"
    assert result.password == "vault-pass"


def test_resolve_alfresco_credentials_falls_back_when_windows_target_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_missing(credential_id: str) -> ProviderCredentials:
        raise AuthenticationError(f"missing {credential_id}")

    monkeypatch.setattr(credentials_module, "load_windows_credential", _raise_missing)
    monkeypatch.setenv("ALFRESCO_USER", "env-user")
    monkeypatch.setenv("ALFRESCO_PASSWORD", "env-pass")

    auth = BridgeAuthContext(mode="winuser", win_user="DOMAIN\\tester")
    result = credentials_module.resolve_alfresco_credentials(
        auth,
        "https://example.test/alfresco",
        provider_config={"credentials": {"mode": "windows", "target": "missing-target"}},
    )

    assert result.username == "env-user"
    assert result.password == "env-pass"


def test_resolve_alfresco_credentials_tries_user_specific_target_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def _load(credential_id: str) -> ProviderCredentials:
        calls.append(credential_id)
        if credential_id == "tc-wfx/bridge/tester":
            return ProviderCredentials(base_url="", username="vault-user", password="vault-pass")
        raise AuthenticationError(f"missing {credential_id}")

    monkeypatch.setattr(credentials_module, "load_windows_credential", _load)

    auth = BridgeAuthContext(mode="winuser", win_user="DOMAIN\\tester")
    result = credentials_module.resolve_alfresco_credentials(
        auth,
        "https://example.test/alfresco",
        provider_config={"credentials": {"mode": "windows", "target": "tc-wfx/bridge"}},
    )

    assert result.username == "vault-user"
    assert result.password == "vault-pass"
    assert calls[0] == "tc-wfx/bridge"
    assert "tc-wfx/bridge/tester" in calls


def test_effective_auth_resolver_uses_connection_credential_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        auth_resolver_module,
        "load_windows_credential",
        lambda credential_id: ProviderCredentials(base_url="", username="vault-user", password=f"{credential_id}-pass"),
    )

    result = auth_resolver_module.resolve_effective_auth(
        {
            "credentials": {
                "mode": "credentials",
                "credential_id": "tc-wfx/webdav",
                "target": "demo/webdav",
                "targetBase": "demo",
                "authScheme": "basic",
            }
        },
        None,
    )

    assert result.mode == "credentials"
    assert result.auth_scheme == "basic"
    assert result.credential_id == "tc-wfx/webdav"
    assert result.target == "demo/webdav"
    assert result.target_base == "demo"
    assert result.username == "vault-user"
    assert result.password == "tc-wfx/webdav-pass"


def test_effective_auth_resolver_supports_shared_target_base_user_variant(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def _load(credential_id: str) -> ProviderCredentials:
        calls.append(credential_id)
        if credential_id == "tc-wfx/company-dms/tester":
            return ProviderCredentials(base_url="", username="tester", password="secret")
        raise AuthenticationError(f"missing {credential_id}")

    monkeypatch.setattr(auth_resolver_module, "load_windows_credential", _load)

    result = auth_resolver_module.resolve_effective_auth(
        {"credentials": {"mode": "windows", "targetBase": "tc-wfx/company-dms"}},
        BridgeAuthContext(mode="winuser", win_user="DOMAIN\\tester"),
    )

    assert result.username == "tester"
    assert result.password == "secret"
    assert calls[0] == "tc-wfx/company-dms"
    assert "tc-wfx/company-dms/tester" in calls


def test_effective_auth_resolver_none_mode_returns_no_headers() -> None:
    result = auth_resolver_module.resolve_effective_auth(
        {"credentials": {"mode": "none", "required": False}},
        None,
    )

    assert result.mode == "none"
    assert result.required is False
    assert result.authorization_headers() == {}


def test_effective_auth_requirements_preserve_configured_public_fields() -> None:
    result = auth_resolver_module.auth_requirements(
        {
            "credentials": {
                "mode": "credentials",
                "credential_id": "tc-wfx/webdav",
                "target": "demo/webdav",
                "targetBase": "demo",
                "authScheme": "bearer",
                "required": True,
            }
        }
    )

    assert result == {
        "mode": "credentials",
        "required": True,
        "credential_id": "tc-wfx/webdav",
        "target": "demo/webdav",
        "targetBase": "demo",
        "authScheme": "bearer",
    }
