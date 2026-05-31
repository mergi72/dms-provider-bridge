from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter

from edocat_bridge.services.transfer_service import copy_item

router = APIRouter()


class TransferRequest(BaseModel):
    source: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    provider: str | None = None


@router.post("/copy")
def transfer_copy(payload: TransferRequest) -> dict:
    result = copy_item(payload.source, payload.destination, provider_name=payload.provider)
    return result.model_dump()
