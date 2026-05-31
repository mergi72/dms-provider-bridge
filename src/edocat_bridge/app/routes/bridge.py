from __future__ import annotations

from fastapi import APIRouter

from edocat_bridge.models.bridge import WfxMoveRequest, WfxPathRequest, WfxShareUrlBrowseRequest, WfxShareUrlRequest, WfxUploadRequest
from edocat_bridge.services.bridge_service import browse_share_url, copy_path, delete_path, download_path, list_path, mkdir_path, rename_path, resolve_share_url, stat_path, upload_path

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


@router.post("/download")
def bridge_download(payload: WfxPathRequest) -> dict:
    return download_path(payload.path, payload.auth).model_dump()


@router.post("/upload")
def bridge_upload(payload: WfxUploadRequest) -> dict:
    return upload_path(
        payload.destination,
        payload.file_name,
        payload.auth,
        content_base64=payload.content_base64,
        overwrite=payload.overwrite,
    ).model_dump()


@router.post("/resolve-share-url")
def bridge_resolve_share_url(payload: WfxShareUrlRequest) -> dict:
    return resolve_share_url(payload.share_url, payload.provider).model_dump()


@router.post("/browse-share-url")
def bridge_browse_share_url(payload: WfxShareUrlBrowseRequest) -> dict:
    return browse_share_url(payload.share_url, payload.auth, payload.provider, payload.operation).model_dump()
