from __future__ import annotations

import base64
from dataclasses import dataclass
from threading import RLock
from typing import Any

from dms_provider_bridge.core.credentials import AuthCredentials, load_windows_credential
from dms_provider_bridge.core.errors import AuthenticationError
from dms_provider_bridge.models.bridge import BridgeAuthContext


_CREDENTIAL_MODES = {"credentials", "windows"}
_CREDENTIAL_CACHE: dict[str, AuthCredentials] = {}
_CREDENTIAL_CACHE_LOCK = RLock()


@dataclass(slots=True)
class EffectiveAuth:
    mode: str
    required: bool
    auth_scheme: str
    credential_id: str | None = None
    target: str | None = None
    target_base: str | None = None
    username: str | None = None
    password: str | None = None
    token: str | None = None
    win_user: str | None = None

    def has_secret(self) -> bool:
        return bool(self.username and (self.password or self.token)) or bool(self.token)

    def as_credentials(self, base_url: str = "") -> AuthCredentials:
        return AuthCredentials(
            base_url=base_url,
            username=self.username,
            password=self.password,
            token=self.token,
        )

    def authorization_headers(self) -> dict[str, str]:
        if self.mode == "none" or self.auth_scheme == "none":
            return {}

        if self.token:
            normalized = self.token.strip()
            if normalized.lower().startswith(("basic ", "bearer ")):
                return {"Authorization": normalized}
            return {"Authorization": f"Bearer {normalized}"}

        if self.auth_scheme == "bearer" and self.password:
            normalized = self.password.strip()
            if normalized.lower().startswith("bearer "):
                return {"Authorization": normalized}
            return {"Authorization": f"Bearer {normalized}"}

        if self.username:
            encoded = base64.b64encode(f"{self.username}:{self.password or ''}".encode("utf-8")).decode("ascii")
            return {"Authorization": f"Basic {encoded}"}

        if self.required:
            raise AuthenticationError("Credentials are missing; live operation cannot continue.")
        return {}


def _normalize_mode(value: object, default: str) -> str:
    mode = str(value or default).strip().lower()
    if mode in _CREDENTIAL_MODES:
        return "credentials"
    if mode == "winuser":
        return "winuser"
    if mode == "none":
        return "none"
    return default


def _public_mode(value: object, default: str) -> str:
    mode = str(value or default).strip()
    return mode or default


def _str_or_none(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _credentials_config(config: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(config, dict):
        return {}

    credentials = config.get("credentials")
    auth = config.get("auth")
    merged: dict[str, Any] = {}
    if isinstance(credentials, dict):
        merged.update(_strip_empty_values(credentials))
    if isinstance(auth, dict):
        merged.update(_strip_empty_values(auth))
    return merged


def _strip_empty_values(config: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in config.items()
        if value not in ("", None)
    }


def _normalize_auth_scheme(value: object, default: str) -> str:
    normalized = str(value or default).strip().lower().replace("-", "_")
    if normalized in {"none", "anonymous"}:
        return "none"
    if normalized in {"bearer", "bearer_token", "oauth2"}:
        return "bearer"
    if normalized in {"ticket", "alfresco_ticket"}:
        return "ticket"
    return "basic"


def _normalize_win_user_variants(win_user: str | None) -> list[str]:
    if not win_user:
        return []
    raw = win_user.strip()
    if not raw:
        return []

    variants = [raw]
    if "\\" in raw:
        _domain, user = raw.split("\\", 1)
        if user:
            variants.append(user)
    elif "@" in raw:
        user = raw.split("@", 1)[0]
        if user:
            variants.append(user)

    deduped: list[str] = []
    for item in variants:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _credential_target_candidates(base_target: str | None, auth: BridgeAuthContext | None) -> list[str]:
    base = (base_target or "").strip()
    if not base:
        return []

    candidates = [base]
    user_variants = _normalize_win_user_variants(auth.win_user if auth else None)
    for user in user_variants:
        candidates.append(f"{base}/{user}")
        candidates.append(f"{base}:{user}")

    deduped: list[str] = []
    for item in candidates:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def _copy_credentials(credentials: AuthCredentials) -> AuthCredentials:
    return AuthCredentials(
        base_url=credentials.base_url,
        username=credentials.username,
        password=credentials.password,
        token=credentials.token,
    )


def clear_credential_cache() -> None:
    with _CREDENTIAL_CACHE_LOCK:
        _CREDENTIAL_CACHE.clear()


def _load_cached_windows_credential(candidate: str) -> AuthCredentials:
    with _CREDENTIAL_CACHE_LOCK:
        cached = _CREDENTIAL_CACHE.get(candidate)
        if cached is not None:
            return _copy_credentials(cached)

    loaded = load_windows_credential(candidate)

    with _CREDENTIAL_CACHE_LOCK:
        _CREDENTIAL_CACHE[candidate] = _copy_credentials(loaded)

    return _copy_credentials(loaded)


def _load_first_available_credential(candidates: list[str]) -> AuthCredentials | None:
    last_error: AuthenticationError | None = None
    for candidate in candidates:
        try:
            return _load_cached_windows_credential(candidate)
        except AuthenticationError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return None


def auth_requirements(config: dict[str, Any] | None, *, default_scheme: str = "basic") -> dict[str, object]:
    credentials = _credentials_config(config)
    mode = _public_mode(credentials.get("mode"), "credentials")
    required_value = credentials.get("required")
    required = bool(required_value) if isinstance(required_value, bool) else mode.lower() != "none"

    result: dict[str, object] = {
        "mode": mode,
        "required": required,
    }
    for key in ("credential_id", "target", "targetBase"):
        value = _str_or_none(credentials.get(key))
        if value:
            result[key] = value

    if "credential_id" not in result and "target" in result:
        result["credential_id"] = result["target"]
    if "target" not in result and "credential_id" in result:
        result["target"] = result["credential_id"]

    _ = default_scheme
    scheme = _str_or_none(credentials.get("authScheme") or credentials.get("scheme") or credentials.get("type"))
    if scheme:
        result["authScheme"] = scheme
    return result


def resolve_effective_auth(
    config: dict[str, Any] | None,
    auth: BridgeAuthContext | None,
    *,
    default_scheme: str = "basic",
    validate_required: bool = True,
) -> EffectiveAuth:
    credentials = _credentials_config(config)
    public_mode = _public_mode(credentials.get("mode"), "credentials")
    mode = _normalize_mode(public_mode, "credentials")
    required_value = credentials.get("required")
    required = bool(required_value) if isinstance(required_value, bool) else mode != "none"

    auth_scheme = _normalize_auth_scheme(
        credentials.get("authScheme") or credentials.get("scheme") or credentials.get("type"),
        default_scheme,
    )
    if mode == "none":
        auth_scheme = "none"

    credential_id = (
        _str_or_none(auth.credential_id if auth else None)
        or _str_or_none(credentials.get("credential_id"))
        or _str_or_none(credentials.get("target"))
    )
    target = _str_or_none(auth.target if auth else None) or _str_or_none(credentials.get("target")) or credential_id
    target_base = _str_or_none(credentials.get("targetBase"))

    effective = EffectiveAuth(
        mode=mode,
        required=required,
        auth_scheme=auth_scheme,
        credential_id=credential_id,
        target=target,
        target_base=target_base,
        username=_str_or_none(auth.username if auth else None),
        password=_str_or_none(auth.password if auth else None),
        token=_str_or_none(auth.token if auth else None),
        win_user=_str_or_none(auth.win_user if auth else None),
    )

    if mode == "none":
        return effective

    if not effective.has_secret():
        bases = [credential_id, target, target_base]
        candidates: list[str] = []
        for base in bases:
            for candidate in _credential_target_candidates(base, auth):
                if candidate not in candidates:
                    candidates.append(candidate)

        if candidates:
            try:
                resolved = _load_first_available_credential(candidates)
            except AuthenticationError:
                resolved = None
            if resolved is not None:
                effective.username = effective.username or resolved.username
                effective.password = effective.password or resolved.password
                effective.token = effective.token or resolved.token

    if validate_required and effective.required and mode == "credentials" and not effective.has_secret():
        ref = effective.credential_id or effective.target or effective.target_base
        if ref:
            raise AuthenticationError(f"Credentials for '{ref}' do not contain usable credentials.")
        raise AuthenticationError("credentials mode requires either credential_id or username + password/token.")

    return effective
