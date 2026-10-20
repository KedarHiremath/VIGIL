"""Telemetry broadcasting and real-time streaming service for VIGIL investigations."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from starlette.websockets import WebSocket, WebSocketState

logger = logging.getLogger(__name__)


class TelemetryManager:
    """Thread-safe telemetry manager broadcasting investigation events to WebSocket clients."""

    def __init__(self, history_maxlen: int = 200) -> None:
        self._history_maxlen = history_maxlen
        self._lock = threading.RLock()
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._history: dict[str, deque[dict[str, Any]]] = defaultdict(
            lambda: deque(maxlen=self._history_maxlen)
        )
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_event_loop(self, loop: asyncio.AbstractEventLoop | None) -> None:
        """Register the running asyncio event loop for thread-safe cross-thread scheduling."""
        with self._lock:
            self._loop = loop

    def get_event_loop(self) -> asyncio.AbstractEventLoop | None:
        """Get the current asyncio loop, or detect if called from an async context."""
        with self._lock:
            if self._loop is not None and not self._loop.is_closed():
                return self._loop
        try:
            loop = asyncio.get_running_loop()
            with self._lock:
                self._loop = loop
            return loop
        except RuntimeError:
            return None

    async def connect(self, investigation_id: str, websocket: WebSocket) -> None:
        """Register a new WebSocket connection and replay recent event history."""
        # Record event loop if not set
        self.get_event_loop()

        with self._lock:
            self._connections[investigation_id].add(websocket)
            history_snapshot = list(self._history[investigation_id])

        # Send connection established event
        welcome_event = {
            "investigation_id": investigation_id,
            "event_type": "subscription_acknowledged",
            "timestamp": datetime.now(UTC).isoformat(),
            "data": {
                "message": f"Connected to telemetry stream for investigation '{investigation_id}'",
                "replayed_events": len(history_snapshot),
            },
        }
        await websocket.send_text(json.dumps(welcome_event))

        # Replay past events in order
        for event in history_snapshot:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_text(json.dumps(event))

    async def disconnect(self, investigation_id: str, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket client."""
        with self._lock:
            if investigation_id in self._connections:
                self._connections[investigation_id].discard(websocket)
                if not self._connections[investigation_id]:
                    del self._connections[investigation_id]

    def broadcast(
        self,
        investigation_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        """Thread-safe dispatch of an event to all connected clients and recording in history."""
        envelope: dict[str, Any] = {
            "investigation_id": investigation_id,
            "event_type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            "data": data,
        }

        with self._lock:
            self._history[investigation_id].append(envelope)
            active_sockets = list(self._connections.get(investigation_id, set()))

        if not active_sockets:
            return

        payload = json.dumps(envelope)
        loop = self.get_event_loop()

        if loop is None or loop.is_closed():
            return

        async def _send(ws: WebSocket, text: str) -> None:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(text)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"Error sending telemetry to websocket: {exc}")
                with self._lock:
                    if investigation_id in self._connections:
                        self._connections[investigation_id].discard(ws)

        for ws in active_sockets:
            try:
                # If currently running on the same loop, create task directly
                try:
                    curr_loop = asyncio.get_running_loop()
                except RuntimeError:
                    curr_loop = None

                if curr_loop is loop:
                    loop.create_task(_send(ws, payload))
                else:
                    asyncio.run_coroutine_threadsafe(_send(ws, payload), loop)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"Failed to dispatch telemetry coroutine: {exc}")

    def create_callback(
        self, investigation_id: str
    ) -> Callable[[str, dict[str, Any]], None]:
        """Create a closure callback suitable for passing to AgenticOrchestrator.run_investigation."""

        def on_event(event_type: str, data: dict[str, Any]) -> None:
            self.broadcast(
                investigation_id=investigation_id,
                event_type=event_type,
                data=data,
            )

        return on_event

    def get_history(self, investigation_id: str) -> list[dict[str, Any]]:
        """Retrieve recent telemetry events for an investigation."""
        with self._lock:
            return list(self._history.get(investigation_id, []))

    def clear(self) -> None:
        """Clear all connections and history (useful in tests)."""
        with self._lock:
            self._connections.clear()
            self._history.clear()
