"""FastAPI application factory for the VIGIL Video Forensics platform."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from vigil.api.dependencies import (
    get_investigation_service,
    get_telemetry_manager,
)
from vigil.api.routes.investigations import router as investigations_router
from vigil.api.routes.websocket import router as websocket_router
from vigil.logging_config import configure_logging
from vigil.storage.repository import EntityNotFoundError

# Install timestamped logging as early as possible so every module that
# calls logging.getLogger(__name__) inherits the correct formatter.
configure_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Lifespan context manager registering active event loop and managing background shutdown."""
    loop = asyncio.get_running_loop()
    telemetry = get_telemetry_manager()
    telemetry.set_event_loop(loop)
    logger.info("VIGIL API services initialized.")
    yield
    logger.info("Shutting down VIGIL API services...")
    service = get_investigation_service()
    service.shutdown(wait=False)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="VIGIL: Autonomous Video-Forensics API",
        description=(
            "API Layer and Real-Time WebSocket Telemetry for autonomous multi-agent video "
            "and acoustic forensic investigation."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS configuration for human investigator review UI
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global Exception Handlers
    @app.exception_handler(EntityNotFoundError)
    async def entity_not_found_handler(
        request: Request, exc: EntityNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )

    # Health and readiness check
    @app.get("/health", tags=["system"])
    @app.get("/api/v1/health", tags=["system"])
    def health_check() -> dict[str, str]:
        return {
            "status": "healthy",
            "service": "VIGIL Video Forensics API",
            "version": "0.1.0",
        }

    # Mount UI static assets and serve dashboard
    ui_dir = Path(__file__).parent.parent / "ui"
    if ui_dir.is_dir():
        app.mount("/ui", StaticFiles(directory=str(ui_dir)), name="ui")

        @app.get("/", tags=["ui"], summary="VIGIL Web UI Mission Control")
        @app.get("/dashboard", tags=["ui"])
        def serve_dashboard() -> FileResponse:
            """Serve interactive VIGIL forensic frontend dashboard."""
            index_file = ui_dir / "index.html"
            return FileResponse(index_file)

    # Include routers
    app.include_router(investigations_router)
    app.include_router(websocket_router)

    return app


app = create_app()
