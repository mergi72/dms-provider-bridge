from __future__ import annotations

import os
from dataclasses import dataclass

from edocat_bridge.models.bridge import BridgeAuthContext


@dataclass(slots=True)
class ProviderCredentials:
    base_url: str
    username: str | None = None
    password: str | None = None
    token: str | None = None


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
