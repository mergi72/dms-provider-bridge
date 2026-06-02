from __future__ import annotations

from fastapi import FastAPI

from edocat_bridge.app.routes.bridge import router as bridge_router
from edocat_bridge.app.routes.edit import router as edit_router
from edocat_bridge.app.routes.health import router as health_router
from edocat_bridge.app.routes.listing import router as listing_router
from edocat_bridge.app.routes.transfer import router as transfer_router


def create_app() -> FastAPI:
    app = FastAPI(title="dms-provider-bridge", version="0.1.0")
    app.include_router(health_router, prefix="/health", tags=["health"])
    app.include_router(listing_router, prefix="/listing", tags=["listing"])
    app.include_router(transfer_router, prefix="/transfer", tags=["transfer"])
    app.include_router(edit_router, prefix="/edit", tags=["edit"])
    app.include_router(bridge_router, prefix="/bridge/wfx", tags=["bridge"])
    return app


app = create_app()
