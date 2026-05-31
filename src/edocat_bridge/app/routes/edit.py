from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from edocat_bridge.services.edit_service import delete_item, rename_item

router = APIRouter()


class RenameRequest(BaseModel):
    source: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    provider: str | None = None


class DeleteRequest(BaseModel):
    target: str = Field(min_length=1)
    provider: str | None = None


@router.post("/rename")
def edit_rename(payload: RenameRequest) -> dict:
    result = rename_item(payload.source, payload.destination, provider_name=payload.provider)
    return result.model_dump()


@router.post("/delete")
def edit_delete(payload: DeleteRequest) -> dict:
    result = delete_item(payload.target, provider_name=payload.provider)
    return result.model_dump()
