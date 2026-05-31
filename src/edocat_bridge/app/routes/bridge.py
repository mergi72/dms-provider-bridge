from __future__ import annotations

from fastapi import APIRouter

from edocat_bridge.models.bridge import WfxMoveRequest, WfxPathRequest, WfxShareUrlBrowseRequest, WfxShareUrlRequest, WfxShareUrlValidateRequest, WfxUploadRequest
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


@router.post(
    "/browse-share-url",
    tags=["Bridge Share URL"],
    operation_id="bridgeBrowseShareUrl",
    summary="Canonical Share URL operation endpoint",
    description=(
        "Canonical endpoint for Share URL flows. Supports execute=true (real execution) "
        "and execute=false (dry-run validation).\n\n"
        "Canonical dry-run example:\n"
        "{\n"
        '  "share_url": "https://.../documentlibrary#/03%20.../Upload?page=1",\n'
        '  "provider": "alfresco",\n'
        '  "operation": "copy",\n'
        '  "execute": false,\n'
        '  "auth": {"mode": "winuser", "win_user": "DOMAIN\\\\user"},\n'
        '  "provider_path_override": "/source/path.txt",\n'
        '  "destination_path_override": "/target/path.txt"\n'
        "}\n\n"
        "Deprecated alias: /browse-share-url-validate"
    ),
)
def bridge_browse_share_url(payload: WfxShareUrlBrowseRequest) -> dict:
    return browse_share_url(
        payload.share_url,
        payload.auth,
        payload.provider,
        payload.operation,
        payload.execute,
        payload.provider_path_override,
        payload.destination_share_url,
        payload.destination_path_override,
        payload.file_name,
        payload.content_base64,
        payload.overwrite,
    ).model_dump()


@router.post(
    "/browse-share-url-validate",
    tags=["Bridge Share URL"],
    operation_id="bridgeBrowseShareUrlValidateDeprecated",
    deprecated=True,
    summary="Deprecated alias for /browse-share-url with execute=false",
    description=(
        "Deprecated endpoint. Use /browse-share-url with execute=false instead.\n\n"
        "Migration example:\n"
        "{\n"
        '  "share_url": "https://.../documentlibrary#/03%20.../Upload?page=1",\n'
        '  "provider": "alfresco",\n'
        '  "operation": "copy",\n'
        '  "execute": false,\n'
        '  "auth": {"mode": "winuser", "win_user": "DOMAIN\\\\user"},\n'
        '  "provider_path_override": "/source/path.txt",\n'
        '  "destination_path_override": "/target/path.txt"\n'
        "}\n"
    ),
)
def bridge_browse_share_url_validate(payload: WfxShareUrlValidateRequest) -> dict:
    return browse_share_url(
        payload.share_url,
        None,
        payload.provider,
        payload.operation,
        False,
        payload.provider_path_override,
        payload.destination_share_url,
        payload.destination_path_override,
        payload.file_name,
    ).model_dump()
