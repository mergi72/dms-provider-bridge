from __future__ import annotations

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse

from dms_provider_bridge.app.routes.bridge import router as bridge_router, share_url_router
from dms_provider_bridge.app.routes.config import router as config_router
from dms_provider_bridge.app.routes.health import router as health_router
from dms_provider_bridge.app.routes.listing import router as listing_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="dms-provider-bridge",
        version="0.8.10-beta",
        description="Local DMS provider bridge API. Config UI is available at /config.",
        docs_url=None,
    )
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
