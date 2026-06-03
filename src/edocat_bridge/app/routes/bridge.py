from __future__ import annotations

from base64 import b64decode
from pathlib import PurePosixPath
from urllib.parse import quote

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from edocat_bridge.models.bridge import WfxMoveRequest, WfxPathRequest, WfxShareUrlBrowseRequest, WfxShareUrlRequest, WfxShareUrlValidateRequest, WfxUploadRequest
from edocat_bridge.services.bridge_service import browse_share_url, copy_path, delete_path, download_path, list_path, mkdir_path, providers_path, rename_path, resolve_share_url, stat_path, upload_path

router = APIRouter()
share_url_router = APIRouter()
RAW_CONTENT_HEADER = "X-Bridge-Raw-Content"


def _build_content_disposition(filename: str) -> str:
    safe_ascii = "".join(ch if 32 <= ord(ch) < 127 and ch not in {'"', '\\'} else "_" for ch in filename)
    if not safe_ascii:
        safe_ascii = "download.bin"
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{safe_ascii}\"; filename*=UTF-8''{encoded}"


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


@router.post("/move")
def bridge_move(payload: WfxMoveRequest) -> dict:
    return rename_path(payload.source, payload.destination, payload.auth).model_dump()


@router.post("/copy")
def bridge_copy(payload: WfxMoveRequest) -> dict:
    return copy_path(payload.source, payload.destination, payload.auth).model_dump()


@router.post("/download")
def bridge_download(payload: WfxPathRequest) -> dict:
    return download_path(payload.path, payload.auth).model_dump()


@router.post("/download-raw")
def bridge_download_raw(payload: WfxPathRequest):
    result = download_path(payload.path, payload.auth)
    if not result.ok:
        return JSONResponse(content=result.model_dump(), headers={RAW_CONTENT_HEADER: "0"})

    data = result.data if isinstance(result.data, dict) else {}
    content_base64 = data.get("content_base64") if isinstance(data, dict) else None
    if not isinstance(content_base64, str) or not content_base64:
        return JSONResponse(content=result.model_dump(), headers={RAW_CONTENT_HEADER: "0"})

    try:
        raw_content = b64decode(content_base64, validate=True)
    except Exception:
        return JSONResponse(content=result.model_dump(), headers={RAW_CONTENT_HEADER: "0"})

    source = data.get("source") if isinstance(data, dict) else None
    filename = PurePosixPath(str(source)).name if isinstance(source, str) and source else "download.bin"
    media_type = data.get("mime_type") if isinstance(data, dict) and isinstance(data.get("mime_type"), str) else "application/octet-stream"
    headers = {
        "Content-Disposition": _build_content_disposition(filename),
        RAW_CONTENT_HEADER: "1",
    }
    return Response(content=raw_content, media_type=media_type, headers=headers)


@router.post("/upload")
def bridge_upload(payload: WfxUploadRequest) -> dict:
    return upload_path(
        payload.destination,
        payload.file_name,
        payload.auth,
        content_base64=payload.content_base64,
        overwrite=payload.overwrite,
    ).model_dump()


@router.get("/providers")
def bridge_providers() -> dict:
    return providers_path().model_dump()


@share_url_router.post(
    "/resolve-share-url",
    operation_id="bridgeResolveShareUrl",
    summary="Resolve Share URL",
)
def bridge_resolve_share_url(payload: WfxShareUrlRequest) -> dict:
    return resolve_share_url(payload.share_url, payload.provider).model_dump()


@share_url_router.post(
    "/browse-share-url",
    operation_id="bridgeBrowseShareUrl",
    summary="Execute Share URL Operation",
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


@share_url_router.post(
    "/browse-share-url-validate",
    operation_id="bridgeBrowseShareUrlValidateDeprecated",
    deprecated=True,
    summary="Deprecated Validate Alias",
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
