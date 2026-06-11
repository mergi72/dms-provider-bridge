from __future__ import annotations

from fastapi import FastAPI

from dms_provider_bridge.app.routes.bridge import router as bridge_router, share_url_router
from dms_provider_bridge.app.routes.edit import router as edit_router
from dms_provider_bridge.app.routes.health import router as health_router
from dms_provider_bridge.app.routes.listing import router as listing_router
from dms_provider_bridge.app.routes.transfer import router as transfer_router


def create_app() -> FastAPI:
    app = FastAPI(title="dms-provider-bridge", version="0.4.11")
    app.include_router(health_router, prefix="/health", tags=["Health"])
    app.include_router(listing_router, prefix="/listing", tags=["Listing"])
    app.include_router(transfer_router, prefix="/transfer", tags=["Transfer"])
    app.include_router(edit_router, prefix="/edit", tags=["Edit"])
    app.include_router(bridge_router, prefix="/bridge/wfx", tags=["Bridge"])
    app.include_router(share_url_router, prefix="/bridge/wfx", tags=["Bridge Share URL"])
    return app


app = create_app()

