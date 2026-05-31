from __future__ import annotations

from fastapi import APIRouter

from edocat_bridge.models.bridge import WfxMoveRequest, WfxPathRequest
from edocat_bridge.services.bridge_service import copy_path, delete_path, list_path, mkdir_path, rename_path, stat_path

router = APIRouter()


@router.post("/list")
def bridge_list(payload: WfxPathRequest) -> dict:
    return list_path(payload.path, payload.auth).model_dump()


@router.post("/stat")
def bridge_stat(payload: WfxPathRequest) -> dict:
    return stat_path(payload.path, payload.auth).model_dump()


@router.post("/mkdir")
def bridge_mkdir(payload: WfxPathRequest) -> dict:
    return mkdir_path(payload.path, payload.auth).model_dump()


@router.post("/delete")
def bridge_delete(payload: WfxPathRequest) -> dict:
    return delete_path(payload.path, payload.auth).model_dump()


@router.post("/rename")
def bridge_rename(payload: WfxMoveRequest) -> dict:
    return rename_path(payload.source, payload.destination, payload.auth).model_dump()


@router.post("/copy")
def bridge_copy(payload: WfxMoveRequest) -> dict:
    return copy_path(payload.source, payload.destination, payload.auth).model_dump()
