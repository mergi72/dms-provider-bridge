from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dms_provider_bridge.core.errors import AuthenticationError, ConnectionNotFoundError, ProviderOperationError
from dms_provider_bridge.services.edit_service import delete_item, rename_item

router = APIRouter()


class RenameRequest(BaseModel):
    source: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    provider: str | None = None
    connection: str | None = None


class DeleteRequest(BaseModel):
    target: str = Field(min_length=1)
    provider: str | None = None
    connection: str | None = None


@router.post("/rename")
def edit_rename(payload: RenameRequest) -> dict:
    try:
        result = rename_item(payload.source, payload.destination, provider_name=payload.provider, connection_name=payload.connection)
        return result.model_dump()
    except (ValueError, ProviderOperationError, AuthenticationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConnectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/delete")
def edit_delete(payload: DeleteRequest) -> dict:
    try:
        result = delete_item(payload.target, provider_name=payload.provider, connection_name=payload.connection)
        return result.model_dump()
    except (ValueError, ProviderOperationError, AuthenticationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConnectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

