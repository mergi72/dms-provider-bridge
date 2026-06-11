from __future__ import annotations

import json
import os
import tempfile
import time
from base64 import b64decode
from pathlib import PurePosixPath
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from dms_provider_bridge.adapters.commander_api import WfxErrorCode
from dms_provider_bridge.core.config_loader import load_config
from dms_provider_bridge.core.logging import get_logger
from dms_provider_bridge.models.bridge import BridgeAuthContext, WfxMoveRequest, WfxPathRequest, WfxShareUrlBrowseRequest, WfxShareUrlRequest, WfxShareUrlValidateRequest, WfxUploadRequest
from dms_provider_bridge.services.bridge_service import copy_path, delete_path, download_path, list_path, mkdir_path, open_download_stream, provider_detail_path, providers_path, rename_path, stat_path, upload_path
from dms_provider_bridge.services.bridge_share_url import browse_share_url, resolve_share_url

router = APIRouter()
share_url_router = APIRouter()
RAW_CONTENT_HEADER = "X-Bridge-Raw-Content"
UPLOAD_RAW_BUFFER_BYTES_DEFAULT = 1024 * 1024
UPLOAD_RAW_BUFFER_BYTES_MIN = 1024 * 1024
UPLOAD_RAW_BUFFER_BYTES_MAX = 4 * 1024 * 1024
UPLOAD_RAW_MAX_BYTES_DEFAULT = 512 * 1024 * 1024
_LOGGER = get_logger(__name__)


def _upload_raw_max_bytes() -> int:
    config = load_config()
    upload_cfg = config.get("upload") if isinstance(config, dict) else None
    raw_cfg = upload_cfg.get("raw") if isinstance(upload_cfg, dict) else None
    value = raw_cfg.get("maxBytes") if isinstance(raw_cfg, dict) else None
    if isinstance(value, int) and value > 0:
        return value
    return UPLOAD_RAW_MAX_BYTES_DEFAULT


def _upload_raw_buffer_bytes() -> int:
    config = load_config()
    upload_cfg = config.get("upload") if isinstance(config, dict) else None
    raw_cfg = upload_cfg.get("raw") if isinstance(upload_cfg, dict) else None
    value = raw_cfg.get("chunkBytes") if isinstance(raw_cfg, dict) else None
    if not isinstance(value, int) or value <= 0:
        return UPLOAD_RAW_BUFFER_BYTES_DEFAULT
    return max(UPLOAD_RAW_BUFFER_BYTES_MIN, min(UPLOAD_RAW_BUFFER_BYTES_MAX, value))


def _build_content_disposition(filename: str) -> str:
    safe_ascii = "".join(ch if 32 <= ord(ch) < 127 and ch not in {'"', '\\'} else "_" for ch in filename)
    if not safe_ascii:
        safe_ascii = "download.bin"
    encoded = quote(filename, safe="")
    return f"attachment; filename=\"{safe_ascii}\"; filename*=UTF-8''{encoded}"


def _iter_raw_stream(stream, chunk_bytes: int = 1024 * 1024):
    try:
        while True:
            chunk = stream.read(chunk_bytes)
            if not chunk:
                break
            yield chunk
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            close()


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
    stream_result = open_download_stream(payload.path, payload.auth)
    if stream_result is not None:
        if not stream_result.ok:
            return JSONResponse(content=stream_result.model_dump(), headers={RAW_CONTENT_HEADER: "0"})
        stream_data = stream_result.data if isinstance(stream_result.data, dict) else {}
        raw_stream = stream_data.get("stream")
        if raw_stream is not None:
            source = stream_data.get("source")
            filename = PurePosixPath(str(source)).name if isinstance(source, str) and source else "download.bin"
            media_type = stream_data.get("mime_type") if isinstance(stream_data.get("mime_type"), str) else "application/octet-stream"
            headers = {
                "Content-Disposition": _build_content_disposition(filename),
                RAW_CONTENT_HEADER: "1",
            }
            size = stream_data.get("size")
            if isinstance(size, int) and size >= 0:
                headers["Content-Length"] = str(size)
            return StreamingResponse(_iter_raw_stream(raw_stream), media_type=media_type, headers=headers)

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
        source_path=payload.source_path,
        overwrite=payload.overwrite,
        versioning=payload.versioning,
    ).model_dump()


@router.post("/upload-raw")
@router.post("/upload-stream")
async def bridge_upload_raw(
    destination: str = Form(...),
    file_name: str = Form(...),
    overwrite: bool = Form(False),
    versioning_json: str | None = Form(None),
    auth_json: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    started_at = time.perf_counter()
    temp_path: str | None = None
    uploaded_bytes = 0
    max_bytes = _upload_raw_max_bytes()
    chunk_bytes = _upload_raw_buffer_bytes()
    rejected = False
    try:
        auth_payload = json.loads(auth_json)
        auth = BridgeAuthContext.model_validate(auth_payload)
    except Exception as exc:
        return {
            "ok": False,
            "error_code": WfxErrorCode.BAD_PATH,
            "message": f"Invalid auth_json payload: {exc}",
            "data": None,
        }

    versioning: dict | None = None
    if versioning_json:
        try:
            parsed_versioning = json.loads(versioning_json)
            if isinstance(parsed_versioning, dict):
                versioning = parsed_versioning
            else:
                raise ValueError("versioning_json must contain a JSON object.")
        except Exception as exc:
            return {
                "ok": False,
                "error_code": WfxErrorCode.BAD_PATH,
                "message": f"Invalid versioning_json payload: {exc}",
                "data": None,
            }

    try:
        suffix = f"-{file_name}" if file_name else ""
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            temp_path = tmp.name
            while True:
                chunk = await file.read(chunk_bytes)
                if not chunk:
                    break
                if uploaded_bytes + len(chunk) > max_bytes:
                    rejected = True
                    return {
                        "ok": False,
                        "error_code": WfxErrorCode.INTERNAL_ERROR,
                        "message": f"Upload blocked: payload size exceeds configured raw limit {max_bytes} B.",
                        "data": None,
                    }
                tmp.write(chunk)
                uploaded_bytes += len(chunk)

        upload_kwargs = {
            "source_path": temp_path,
            "overwrite": overwrite,
        }
        if versioning is not None:
            upload_kwargs["versioning"] = versioning
        response = upload_path(
            destination,
            file_name,
            auth,
            **upload_kwargs,
        )
        return response.model_dump()
    finally:
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        if rejected:
            _LOGGER.warning(
                "bridge_upload_raw_rejected destination=%s file=%s bytes=%d max_bytes=%d duration_ms=%d",
                destination,
                file_name,
                uploaded_bytes,
                max_bytes,
                duration_ms,
            )
        else:
            _LOGGER.info(
                "bridge_upload_raw destination=%s file=%s bytes=%d max_bytes=%d chunk_bytes=%d duration_ms=%d",
                destination,
                file_name,
                uploaded_bytes,
                max_bytes,
                chunk_bytes,
                duration_ms,
            )
        await file.close()
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                _LOGGER.warning("bridge_upload_raw cleanup_failed path=%s", temp_path)


@router.get("/providers")
def bridge_providers() -> dict:
    payload = providers_path().model_dump()
    data = payload.get("data")
    if isinstance(data, dict):
        payload["providers"] = data.get("providers", [])
        payload["default_provider"] = data.get("default_provider")
    return payload


@router.get("/providers/{provider_name}")
def bridge_provider_detail(provider_name: str) -> dict:
    return provider_detail_path(provider_name).model_dump()


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
        payload.versioning,
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

