"""WebSocket routes streaming live investigation telemetry to connected investigators."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from vigil.api.dependencies import get_telemetry_manager
from vigil.services.telemetry import TelemetryManager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["telemetry"])


async def handle_telemetry_stream(
    websocket: WebSocket,
    investigation_id: str,
    telemetry: TelemetryManager,
) -> None:
    """Accept WebSocket connection, replay events, and stream real-time updates."""
    await websocket.accept()
    await telemetry.connect(investigation_id, websocket)
    logger.info(
        f"WebSocket client connected to telemetry stream for '{investigation_id}'"
    )

    try:
        while True:
            # Keep connection alive and accept incoming messages (e.g. pings)
            message = await websocket.receive_text()
            if message.strip().lower() == "ping":
                await websocket.send_text('{"event_type": "pong"}')
    except (WebSocketDisconnect, ConnectionResetError):
        logger.info(
            f"WebSocket client disconnected from investigation '{investigation_id}'"
        )
    finally:
        await telemetry.disconnect(investigation_id, websocket)


@router.websocket("/api/v1/investigations/{investigation_id}/telemetry")
async def investigation_telemetry_ws(
    websocket: WebSocket,
    investigation_id: str,
    telemetry: Annotated[TelemetryManager, Depends(get_telemetry_manager)],
) -> None:
    """Stream live agent actions, newly detected observations,

    event correlations, and coverage updates in real-time.
    """
    await handle_telemetry_stream(websocket, investigation_id, telemetry)


@router.websocket("/ws/investigations/{investigation_id}")
async def investigation_ws_alias(
    websocket: WebSocket,
    investigation_id: str,
    telemetry: Annotated[TelemetryManager, Depends(get_telemetry_manager)],
) -> None:
    """Convenience alias route for WebSocket telemetry."""
    await handle_telemetry_stream(websocket, investigation_id, telemetry)

