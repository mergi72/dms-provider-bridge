from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse

from dms_provider_bridge.app.routes.bridge import router as bridge_router, share_url_router
from dms_provider_bridge.app.routes.config import router as config_router
from dms_provider_bridge.app.routes.health import router as health_router
from dms_provider_bridge.app.routes.listing import router as listing_router
from dms_provider_bridge.tracing import CORRELATION_HEADER, correlation_scope


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _request_is_local(request) -> bool:
    client_host = request.client.host if request.client is not None else ""
    if client_host == "testclient":
        return True
    try:
        return ipaddress.ip_address(client_host).is_loopback
    except ValueError:
        return False


def _config_request_allowed(request) -> bool:
    hostname = (request.url.hostname or "").casefold()
    if hostname == "testserver":
        return True
    if hostname not in _LOOPBACK_HOSTS:
        return False
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return True
    origin = request.headers.get("origin")
    if not origin:
        return False
    try:
        parsed_origin = urlsplit(origin)
        return (
            parsed_origin.scheme == request.url.scheme
            and parsed_origin.hostname is not None
            and parsed_origin.hostname.casefold() == hostname
            and parsed_origin.port == request.url.port
        )
    except ValueError:
        return False


def create_app() -> FastAPI:
    app = FastAPI(
        title="dms-provider-bridge",
        version="1.1.7",
        description="Local DMS provider bridge API. Config UI is available at /config.",
        docs_url=None,
    )

    @app.middleware("http")
    async def correlation_middleware(request, call_next):
        with correlation_scope(request.headers.get(CORRELATION_HEADER)) as correlation_id:
            if not _request_is_local(request):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Bridge accepts requests only from the local machine."},
                    headers={CORRELATION_HEADER: correlation_id},
                )
            if request.url.path.startswith("/config") and not _config_request_allowed(request):
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Config UI accepts only same-origin localhost requests."},
                    headers={CORRELATION_HEADER: correlation_id},
                )
            response = await call_next(request)
            response.headers[CORRELATION_HEADER] = correlation_id
            return response

    app.include_router(health_router, prefix="/health", tags=["Health"])
    app.include_router(listing_router, prefix="/listing", tags=["Listing"])
    app.include_router(bridge_router, prefix="/bridge/wfx", tags=["Bridge"])
    app.include_router(share_url_router, prefix="/bridge/wfx", tags=["Bridge Share URL"])
    app.include_router(config_router, prefix="/config", tags=["Config"])

    @app.get("/docs", include_in_schema=False)
    def swagger_docs() -> HTMLResponse:
        response = get_swagger_ui_html(
            openapi_url=str(app.openapi_url),
            title=f"{app.title} - Swagger UI",
            swagger_favicon_url="https://fastapi.tiangolo.com/img/favicon.png",
        )
        content = response.body.decode("utf-8")
        nav = (
            '<div style="padding:10px 20px;background:#1f2933;color:white;'
            'font-family:Segoe UI,Arial,sans-serif;">'
            '<strong>DMS Provider Bridge</strong>'
            '<a href="/config" style="margin-left:18px;color:white;">Config</a>'
            '<a href="/health" style="margin-left:12px;color:white;">Health</a>'
            "</div>"
        )
        return HTMLResponse(content.replace("<body>", f"<body>{nav}"))

    return app


app = create_app()
