from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from edocat_bridge.core.errors import AuthenticationError, ProviderNotFoundError, ProviderOperationError
from edocat_bridge.services.transfer_service import copy_item

router = APIRouter()


class TransferRequest(BaseModel):
    source: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    provider: str | None = None


@router.post("/copy")
def transfer_copy(payload: TransferRequest) -> dict:
    try:
        result = copy_item(payload.source, payload.destination, provider_name=payload.provider)
        return result.model_dump()
    except (ValueError, ProviderOperationError, AuthenticationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ProviderNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
