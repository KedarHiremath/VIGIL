"""Unit tests for Phase 5 review workflow, audit, and report export REST endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.media_test_helpers import create_test_video
from vigil.api.app import create_app
from vigil.api.dependencies import (
    get_investigation_service,
    get_telemetry_manager,
)
from vigil.domain.artifact import Artifact
from vigil.domain.event import Event
from vigil.domain.investigation import Investigation
from vigil.domain.media_asset import MediaAsset
from vigil.domain.report import Report
from vigil.domain.source_reference import SourceReference
from vigil.models.mock import MockLLMClient
from vigil.orchestration.investigation_state import (
    InvestigationState,
    InvestigationStatus,
)
from vigil.services.investigation_service import InvestigationService
from vigil.services.telemetry import TelemetryManager
from vigil.storage.sqlite_repository import SqliteInvestigationRepository


@pytest.fixture
def review_setup(tmp_path: Path):
    """Setup in-memory environment with sample investigation, events, and mock dependencies."""
    repo = SqliteInvestigationRepository(":memory:")
    telemetry = TelemetryManager()
    service = InvestigationService(
        repository=repo,
        telemetry=telemetry,
        storage_dir=tmp_path / "storage",
    )
    service.orchestrator.llm = MockLLMClient()

    # Create dummy video file
    video_file = tmp_path / "feed.mp4"
    create_test_video(video_file, duration_seconds=4.0, fps=24)

    media_asset = MediaAsset(
        media_asset_id="media-test-01",
        media_type="video",
        storage_uri=video_file.as_uri(),
        duration_seconds=4.0,
    )
    repo.add_media_asset(media_asset)

    inv = Investigation(
        investigation_id="inv-rev-test",
        title="Review API Test Investigation",
        objective="Identify security breaches",
        scope_description="Perimeter surveillance",
        media_asset_ids=["media-test-01"],
    )
    repo.add_investigation(inv)

    event1 = Event(
        event_id="evt-test-01",
        event_type="restricted_entry",
        description="Subject crosses yellow line.",
        observation_ids=["obs-test-01"],
        status="proposed",
        start_seconds=1.0,
        end_seconds=2.5,
    )
    event2 = Event(
        event_id="evt-test-02",
        event_type="noise_trigger",
        description="Loud crash sound.",
        observation_ids=["obs-test-02"],
        status="proposed",
        start_seconds=2.6,
        end_seconds=3.2,
    )
    repo.add_event(event1)
    repo.add_event(event2)

    now = datetime.now(UTC)
    state = InvestigationState(
        investigation_id="inv-rev-test",
        status=InvestigationStatus.COMPLETED,
        completed_at=now,
        event_ids=["evt-test-01", "evt-test-02"],
        observation_ids=["obs-test-01", "obs-test-02"],
    )
    repo.save_state(state)

    report = Report(
        report_id="rep-test-01",
        investigation_id="inv-rev-test",
        title="Initial Draft Report",
        summary="Automated agent analysis recorded 2 events.",
        generated_by="vigil-agent",
        version=1,
        status="draft",
    )
    repo.add_report(report)

    app = create_app()
    app.dependency_overrides[get_investigation_service] = lambda: service
    app.dependency_overrides[get_telemetry_manager] = lambda: telemetry

    client = TestClient(app)
    try:
        yield client, service, video_file
    finally:
        service.shutdown(wait=False)


def test_review_event_endpoints(review_setup) -> None:
    client, _service, _ = review_setup

    # 1. POST review event -> confirmed
    res = client.post(
        "/api/v1/investigations/inv-rev-test/events/evt-test-01/review",
        json={
            "status": "confirmed",
            "reviewer": "investigator-dan",
            "notes": "Verified badge unauthorized on camera.",
            "description": "Unauthorized worker entered restricted bay.",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["event"]["status"] == "confirmed"
    assert data["event"]["reviewer"] == "investigator-dan"
    assert data["event"]["description"] == "Unauthorized worker entered restricted bay."
    assert data["audit_log"]["action"] == "event_review"
    assert data["audit_log"]["changes"]["status"]["new"] == "confirmed"

    # 2. POST review event 2 -> rejected
    res2 = client.post(
        "/api/v1/investigations/inv-rev-test/events/evt-test-02/review",
        json={
            "status": "rejected",
            "reviewer": "investigator-dan",
            "notes": "Normal machinery operation sound.",
        },
    )
    assert res2.status_code == 200
    assert res2.json()["event"]["status"] == "rejected"

    # 3. GET events with status filter
    res_conf = client.get("/api/v1/investigations/inv-rev-test/events?status=confirmed")
    assert res_conf.status_code == 200
    assert len(res_conf.json()) == 1
    assert res_conf.json()[0]["event_id"] == "evt-test-01"

    res_rej = client.get("/api/v1/investigations/inv-rev-test/events?status=rejected")
    assert res_rej.status_code == 200
    assert len(res_rej.json()) == 1
    assert res_rej.json()[0]["event_id"] == "evt-test-02"

    # 4. GET single event
    res_single = client.get("/api/v1/investigations/inv-rev-test/events/evt-test-01")
    assert res_single.status_code == 200
    assert res_single.json()["status"] == "confirmed"


def test_edit_event_endpoint(review_setup) -> None:
    client, _service, _ = review_setup

    res = client.patch(
        "/api/v1/investigations/inv-rev-test/events/evt-test-01",
        json={
            "editor": "investigator-sarah",
            "description": "Edited description: Subject in hi-vis jacket.",
            "start_seconds": 1.2,
            "end_seconds": 2.4,
            "notes": "Tightened time bounds.",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["event"]["description"] == "Edited description: Subject in hi-vis jacket."
    assert data["event"]["start_seconds"] == 1.2
    assert data["event"]["end_seconds"] == 2.4
    assert data["audit_log"]["action"] == "event_edit"


def test_audit_logs_query_endpoint(review_setup) -> None:
    client, _service, _ = review_setup

    client.post(
        "/api/v1/investigations/inv-rev-test/events/evt-test-01/review",
        json={
            "status": "confirmed",
            "reviewer": "investigator-dan",
            "notes": "Confirmed",
        },
    )

    res = client.get("/api/v1/investigations/inv-rev-test/audit")
    assert res.status_code == 200
    logs = res.json()
    assert len(logs) >= 1
    assert logs[0]["target_id"] == "evt-test-01"
    assert logs[0]["actor"] == "investigator-dan"


def test_finalize_and_export_endpoints(review_setup) -> None:
    client, _service, _ = review_setup

    # First confirm an event so an incident clip is sliced during finalization
    client.post(
        "/api/v1/investigations/inv-rev-test/events/evt-test-01/review",
        json={
            "status": "confirmed",
            "reviewer": "lead-agent-smith",
            "notes": "Confirmed incident on tape.",
        },
    )

    res_fin = client.post(
        "/api/v1/investigations/inv-rev-test/report/finalize",
        json={
            "finalized_by": "lead-agent-smith",
            "notes": "Full review complete, clips compiled.",
            "auto_slice_clips": True,
        },
    )
    assert res_fin.status_code == 200
    fin_data = res_fin.json()
    assert fin_data["version"] == 2
    assert fin_data["report"]["status"] == "finalized"
    assert fin_data["report"]["finalized_by"] == "lead-agent-smith"

    # Export HTML
    res_html = client.get("/api/v1/investigations/inv-rev-test/export/html")
    assert res_html.status_code == 200
    assert "text/html" in res_html.headers["content-type"]
    assert "VIGIL Forensic Report" in res_html.text
    assert "<video" in res_html.text

    # Export PDF
    res_pdf = client.get("/api/v1/investigations/inv-rev-test/export/pdf")
    assert res_pdf.status_code == 200
    assert "application/pdf" in res_pdf.headers["content-type"]
    assert res_pdf.content.startswith(b"%PDF-")

    # Format query on /report
    res_rep_html = client.get("/api/v1/investigations/inv-rev-test/report?format=html")
    assert res_rep_html.status_code == 200
    assert "text/html" in res_rep_html.headers["content-type"]

    res_rep_pdf = client.get("/api/v1/investigations/inv-rev-test/report?format=pdf")
    assert res_rep_pdf.status_code == 200
    assert "application/pdf" in res_rep_pdf.headers["content-type"]


def test_artifact_content_streaming(review_setup) -> None:
    client, _service, video_file = review_setup

    art = Artifact(
        artifact_id="art-stream-01",
        artifact_type="clip",
        media_type="video",
        storage_uri=video_file.as_uri(),
        source_reference=SourceReference(
            media_asset_id="media-test-01", start_seconds=0.0, end_seconds=2.0
        ),
    )
    _service.repository.add_artifact(art)

    res = client.get("/api/v1/investigations/inv-rev-test/artifacts/art-stream-01/content")
    assert res.status_code == 200
    assert "video/mp4" in res.headers["content-type"]
    assert len(res.content) > 0
