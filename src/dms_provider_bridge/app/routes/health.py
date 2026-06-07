from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter

from dms_provider_bridge.core.logging import get_logger
from dms_provider_bridge.services.version_service import get_version

router = APIRouter()
logger = get_logger(__name__)


@router.get("")
def health() -> dict[str, str]:
    payload = {
        "status": "ok",
        "service": "dms-provider-bridge",
        "version": get_version(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.info("Health check OK: %s", payload)
    return payload

