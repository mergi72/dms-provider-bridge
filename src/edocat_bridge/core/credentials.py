from __future__ import annotations

import ctypes
import json
import os
import platform
from dataclasses import dataclass

from ctypes import POINTER, byref, string_at
from ctypes import wintypes

from edocat_bridge.core.errors import AuthenticationError
from edocat_bridge.models.bridge import BridgeAuthContext


@dataclass(slots=True)
class ProviderCredentials:
    base_url: str
    username: str | None = None
    password: str | None = None
    token: str | None = None


class _CREDENTIAL_ATTRIBUTEW(ctypes.Structure):
    _fields_ = [
        ("Keyword", wintypes.LPWSTR),
        ("Flags", wintypes.DWORD),
        ("ValueSize", wintypes.DWORD),
        ("Value", ctypes.c_void_p),
    ]


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.c_void_p),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", POINTER(_CREDENTIAL_ATTRIBUTEW)),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def _decode_credential_blob(blob: bytes) -> str:
    candidates = ("utf-8", "utf-16-le", "utf-16")
    for encoding in candidates:
        try:
            decoded = blob.decode(encoding).strip("\x00").strip()
        except UnicodeDecodeError:
            continue
        if decoded and "\x00" not in decoded:
            return decoded
    return blob.decode("latin-1", errors="ignore").strip("\x00").strip()


def _load_windows_generic_credential(credential_id: str) -> ProviderCredentials:
    if platform.system().lower() != "windows":
        raise AuthenticationError("Windows Credential Manager is available only on Windows.")

    advapi32 = ctypes.WinDLL("Advapi32", use_last_error=True)
    cred_read = advapi32.CredReadW
    cred_read.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(_CREDENTIALW))]
    cred_read.restype = wintypes.BOOL

    cred_free = advapi32.CredFree
    cred_free.argtypes = [ctypes.c_void_p]
    cred_free.restype = None

    cred_ptr = ctypes.POINTER(_CREDENTIALW)()
    if not cred_read(credential_id, 1, 0, byref(cred_ptr)):
        error_code = ctypes.get_last_error()
        raise AuthenticationError(
            f"Windows Credential Manager entry '{credential_id}' could not be read: {ctypes.WinError(error_code)}"
        )

    try:
        credential = cred_ptr.contents
        username = credential.UserName.strip() if credential.UserName else None
        secret: str | None = None
        if credential.CredentialBlob and credential.CredentialBlobSize:
            blob = string_at(credential.CredentialBlob, credential.CredentialBlobSize)
            secret = _decode_credential_blob(blob)

        if secret:
            try:
                parsed = json.loads(secret)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, dict):
                return ProviderCredentials(
                    base_url=str(parsed.get("base_url") or ""),
                    username=str(parsed.get("username") or username) if (parsed.get("username") or username) else None,
                    password=str(parsed.get("password")) if parsed.get("password") is not None else None,
                    token=str(parsed.get("token")) if parsed.get("token") is not None else None,
                )

        return ProviderCredentials(base_url="", username=username, password=secret)
    finally:
        cred_free(cred_ptr)


def load_alfresco_credentials() -> ProviderCredentials:
    return ProviderCredentials(
        base_url=os.getenv("ALFRESCO_URL", ""),
        username=os.getenv("ALFRESCO_USER"),
        password=os.getenv("ALFRESCO_PASSWORD"),
    )


def load_edocat_credentials() -> ProviderCredentials:
    return ProviderCredentials(
        base_url=os.getenv("EDOCAT_URL", ""),
        token=os.getenv("EDOCAT_TOKEN"),
    )


def load_windows_credential(credential_id: str) -> ProviderCredentials:
    credential = _load_windows_generic_credential(credential_id)
    credential.base_url = credential.base_url or ""
    return credential


def resolve_alfresco_credentials(auth: BridgeAuthContext | None, base_url: str) -> ProviderCredentials:
    if auth is None:
        return ProviderCredentials(
            base_url=base_url or os.getenv("ALFRESCO_URL", ""),
            username=os.getenv("ALFRESCO_USER"),
            password=os.getenv("ALFRESCO_PASSWORD"),
            token=os.getenv("ALFRESCO_TICKET"),
        )

    username = auth.username or auth.win_user or os.getenv("ALFRESCO_USER")
    password = auth.password or os.getenv("ALFRESCO_PASSWORD")
    token = auth.token or os.getenv("ALFRESCO_TICKET")
    return ProviderCredentials(
        base_url=base_url or os.getenv("ALFRESCO_URL", ""),
        username=username,
        password=password,
        token=token,
    )
