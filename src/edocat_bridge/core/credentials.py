from __future__ import annotations

import os
from dataclasses import dataclass


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
