from __future__ import annotations

# pyright: reportMissingTypeStubs=false

import pytest

import edocat_bridge.services.auth_service as auth_service_module  # type: ignore[import-untyped]
from edocat_bridge.core.credentials import ProviderCredentials  # type: ignore[import-untyped]
from edocat_bridge.core.errors import AuthenticationError  # type: ignore[import-untyped]
from edocat_bridge.models.bridge import BridgeAuthContext  # type: ignore[import-untyped]


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


def test_validate_bridge_auth_requires_credentials_or_credential_id() -> None:
    auth = BridgeAuthContext(mode="credentials")

    with pytest.raises(AuthenticationError, match="credentials mode requires either credential_id"):
        auth_service_module.validate_bridge_auth(auth)