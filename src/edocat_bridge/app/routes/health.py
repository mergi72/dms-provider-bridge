from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from edocat_bridge.services.version_service import get_version

router = APIRouter()


@router.get("")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "edocat-bridge",
        "version": get_version(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
