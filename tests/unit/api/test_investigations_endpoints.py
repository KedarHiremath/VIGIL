"""Unit tests for VIGIL FastAPI REST endpoints."""

from __future__ import annotations

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
def test_setup(tmp_path: Path):
    """Create isolated test environment with in-memory SQLite and mock LLM."""
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
        yield client, service, tmp_path
    finally:
        service.shutdown(wait=False)


def test_health_endpoints(test_setup) -> None:
    client, _, _ = test_setup
    r1 = client.get("/health")
    assert r1.status_code == 200
    assert r1.json()["status"] == "healthy"

    r2 = client.get("/api/v1/health")
    assert r2.status_code == 200
    assert r2.json()["service"] == "VIGIL Video Forensics API"


def test_post_investigations_missing_input(test_setup) -> None:
    client, _, _ = test_setup
    res = client.post("/api/v1/investigations", data={})
    assert res.status_code == 400
    assert "Either a video file upload or a valid file_path is required" in res.json()["detail"]


def test_post_investigations_invalid_file_path(test_setup, tmp_path: Path) -> None:
    client, _, _ = test_setup
    missing_file = tmp_path / "does_not_exist.mp4"
    res = client.post(
        "/api/v1/investigations",
        data={"file_path": str(missing_file)},
    )
    assert res.status_code == 400
    assert "does not exist" in res.json()["detail"]


def test_post_investigations_with_file_upload_sync(test_setup) -> None:
    client, _service, tmp_path = test_setup
    video_path = tmp_path / "upload_sample.mp4"
    create_test_video(video_path, duration_seconds=1.0, fps=24, with_audio=True)

    with open(video_path, "rb") as f:
        res = client.post(
            "/api/v1/investigations",
            files={"file": ("upload_sample.mp4", f, "video/mp4")},
            data={
                "title": "Uploaded Breach Footage",
                "objective": "Identify intruders",
                "camera_id": "cam-gate-01",
                "sample_interval_seconds": "0.5",
                "max_frames": "3",
                "run_async": "false",
            },
        )

    assert res.status_code == 202
    data = res.json()
    assert "investigation_id" in data
    assert data["title"] == "Uploaded Breach Footage"
    assert data["camera_id"] == "cam-gate-01"
    assert data["frame_count"] > 0
    assert data["status"] == "completed"

    inv_id = data["investigation_id"]

    # 1. Check status endpoint
    status_res = client.get(f"/api/v1/investigations/{inv_id}/status")
    assert status_res.status_code == 200
    st_data = status_res.json()
    assert st_data["status"] == "completed"
    assert st_data["has_report"] is True
    assert st_data["observation_count"] > 0
    assert st_data["event_count"] > 0

    # 2. Check report endpoint (JSON)
    rep_res = client.get(f"/api/v1/investigations/{inv_id}/report")
    assert rep_res.status_code == 200
    rep_data = rep_res.json()
    assert rep_data["investigation_id"] == inv_id
    assert rep_data["summary"] != ""

    # 3. Check report endpoint (Markdown)
    rep_md_res = client.get(f"/api/v1/investigations/{inv_id}/report?format=markdown")
    assert rep_md_res.status_code == 200
    assert "text/markdown" in rep_md_res.headers["content-type"]
    assert "# " in rep_md_res.text
    assert "Executive Summary" in rep_md_res.text

    # 4. Check list investigations
    list_res = client.get("/api/v1/investigations")
    assert list_res.status_code == 200
    items = list_res.json()
    assert len(items) == 1
    assert items[0]["investigation_id"] == inv_id

    # 5. Check investigation details
    det_res = client.get(f"/api/v1/investigations/{inv_id}")
    assert det_res.status_code == 200
    assert det_res.json()["investigation_id"] == inv_id

    # 6. Check query sub-endpoints
    obs_res = client.get(f"/api/v1/investigations/{inv_id}/observations")
    assert obs_res.status_code == 200
    assert len(obs_res.json()) > 0

    evt_res = client.get(f"/api/v1/investigations/{inv_id}/events")
    assert evt_res.status_code == 200
    assert len(evt_res.json()) > 0

    cov_res = client.get(f"/api/v1/investigations/{inv_id}/coverage")
    assert cov_res.status_code == 200
    assert len(cov_res.json()) > 0

    art_res = client.get(f"/api/v1/investigations/{inv_id}/artifacts")
    assert art_res.status_code == 200
    assert len(art_res.json()) > 0


def test_get_report_conflict_when_running(test_setup, tmp_path: Path) -> None:
    client, service, _ = test_setup
    video_path = tmp_path / "running_test.mp4"
    create_test_video(video_path, duration_seconds=1.0)

    # Ingest without running
    inv, _ = service.create_and_ingest_investigation(
        file_path=video_path,
        title="Pending Run",
    )

    # State is CREATED -> report query should return 409 Conflict
    res = client.get(f"/api/v1/investigations/{inv.investigation_id}/report")
    assert res.status_code == 409
    assert "Report has not yet been generated" in res.json()["detail"]


def test_endpoints_404_not_found(test_setup) -> None:
    client, _, _ = test_setup
    assert client.get("/api/v1/investigations/unknown-id/status").status_code == 404
    assert client.get("/api/v1/investigations/unknown-id/report").status_code == 404
    assert client.get("/api/v1/investigations/unknown-id").status_code == 404
    assert client.get("/api/v1/investigations/unknown-id/observations").status_code == 404
    assert client.get("/api/v1/investigations/unknown-id/events").status_code == 404
    assert client.get("/api/v1/investigations/unknown-id/coverage").status_code == 404
    assert client.get("/api/v1/investigations/unknown-id/artifacts").status_code == 404


def test_dashboard_endpoints(test_setup) -> None:
    client, _, _ = test_setup
    r1 = client.get("/")
    assert r1.status_code == 200
    assert "VIGIL" in r1.text
    assert "MISSION CONTROL" in r1.text

    r2 = client.get("/dashboard")
    assert r2.status_code == 200
    assert "VIGIL" in r2.text
