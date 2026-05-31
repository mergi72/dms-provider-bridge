from __future__ import annotations

import os

from edocat_bridge.core.errors import AuthenticationError
from edocat_bridge.models.bridge import BridgeAuthContext


def validate_bridge_auth(auth: BridgeAuthContext) -> BridgeAuthContext:
    if auth.mode == "credentials":
        has_credential_ref = bool(auth.credential_id)
        has_user_secret = bool(auth.username and (auth.password or auth.token))
        if not has_credential_ref and not has_user_secret:
            raise AuthenticationError(
                "credentials mode requires either credential_id or username + password/token."
            )
        return auth

    if auth.mode == "winuser":
        if auth.win_user:
            return auth
        # Fallback for local debug when plugin omits explicit user value.
        env_user = os.getenv("USERNAME")
        env_domain = os.getenv("USERDOMAIN")
        if env_user:
            auth.win_user = f"{env_domain}\\{env_user}" if env_domain else env_user
            return auth
        raise AuthenticationError("winuser mode requires win_user.")

    raise AuthenticationError(f"Unsupported auth mode: {auth.mode}")
