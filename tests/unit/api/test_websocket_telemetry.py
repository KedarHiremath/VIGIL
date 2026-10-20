"""Unit tests for VIGIL WebSocket real-time telemetry streaming."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.media_test_helpers import create_test_video
from vigil.api.app import create_app
from vigil.api.dependencies import (
    get_investigation_service,
    get_telemetry_manager,
)
from vigil.models.mock import MockLLMClient
from vigil.services.investigation_service import InvestigationService
from vigil.services.telemetry import TelemetryManager
from vigil.storage.sqlite_repository import SqliteInvestigationRepository


@pytest.fixture
def ws_test_setup(tmp_path: Path):
    """Fixture providing app and client with WebSocket support."""
    repo = SqliteInvestigationRepository(":memory:")
    telemetry = TelemetryManager()
    service = InvestigationService(
        repository=repo,
        telemetry=telemetry,
        storage_dir=tmp_path / "storage",
    )
    service.orchestrator.llm = MockLLMClient()

    app = create_app()
    app.dependency_overrides[get_investigation_service] = lambda: service
    app.dependency_overrides[get_telemetry_manager] = lambda: telemetry

    client = TestClient(app)
    try:
        yield client, service, telemetry, tmp_path
    finally:
        service.shutdown(wait=False)


def test_websocket_connect_and_ping(ws_test_setup) -> None:
    client, _, _, _ = ws_test_setup
    inv_id = "inv-ws-ping"

    with client.websocket_connect(f"/api/v1/investigations/{inv_id}/telemetry") as ws:
        # First message is connection acknowledgment
        init_data = json.loads(ws.receive_text())
        assert init_data["event_type"] == "subscription_acknowledged"
        assert init_data["investigation_id"] == inv_id

        # Send ping
        ws.send_text("ping")
        pong = json.loads(ws.receive_text())
        assert pong["event_type"] == "pong"


def test_websocket_alias_and_event_replay(ws_test_setup) -> None:
    client, _, telemetry, _ = ws_test_setup
    inv_id = "inv-ws-replay"

    # Pre-populate some history in telemetry before client connects
    telemetry.broadcast(inv_id, "pre_event_1", {"index": 1})
    telemetry.broadcast(inv_id, "pre_event_2", {"index": 2})

    with client.websocket_connect(f"/ws/investigations/{inv_id}") as ws:
        # 1. Welcome message
        welcome = json.loads(ws.receive_text())
        assert welcome["event_type"] == "subscription_acknowledged"
        assert welcome["data"]["replayed_events"] == 2

        # 2. Replayed event 1
        ev1 = json.loads(ws.receive_text())
        assert ev1["event_type"] == "pre_event_1"
        assert ev1["data"]["index"] == 1

        # 3. Replayed event 2
        ev2 = json.loads(ws.receive_text())
        assert ev2["event_type"] == "pre_event_2"
        assert ev2["data"]["index"] == 2


def test_websocket_live_investigation_streaming(ws_test_setup) -> None:
    client, service, _, tmp_path = ws_test_setup
    video_path = tmp_path / "ws_stream.mp4"
    create_test_video(video_path, duration_seconds=1.0, fps=24, with_audio=False)

    inv, _ = service.create_and_ingest_investigation(
        file_path=video_path,
        title="Live WebSocket Stream Test",
        sample_interval_seconds=0.5,
        max_frames=3,
    )
    inv_id = inv.investigation_id

    received_event_types: list[str] = []

    with client.websocket_connect(f"/api/v1/investigations/{inv_id}/telemetry") as ws:
        # Initial ack
        ack = json.loads(ws.receive_text())
        assert ack["event_type"] == "subscription_acknowledged"

        # Run investigation synchronously (which dispatches events to telemetry)
        service.run_investigation(inv_id, run_async=False)

        # Collect live streamed messages
        while True:
            try:
                # Use a small timeout or non-blocking check
                raw = ws.receive_text()
                data = json.loads(raw)
                received_event_types.append(data["event_type"])
                if data["event_type"] == "investigation_completed":
                    break
            except Exception:  # noqa: BLE001
                break

    # Verify all expected lifecycle telemetry events were received
    assert "state_changed" in received_event_types
    assert "plan_created" in received_event_types
    assert "task_started" in received_event_types
    assert "task_completed" in received_event_types
    assert "observation_detected" in received_event_types
    assert "investigation_completed" in received_event_types
