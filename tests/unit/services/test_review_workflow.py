"""Unit tests for Phase 5 review workflow in InvestigationService."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from tests.media_test_helpers import create_test_video
from vigil.domain.event import Event
from vigil.domain.investigation import Investigation
from vigil.domain.media_asset import MediaAsset
from vigil.orchestration.investigation_state import (
    InvestigationState,
    InvestigationStatus,
)
from vigil.services.investigation_service import InvestigationService
from vigil.storage.sqlite_repository import SqliteInvestigationRepository


def test_review_event_workflow(tmp_path: Path) -> None:
    repo = SqliteInvestigationRepository(":memory:")
    service = InvestigationService(repository=repo, storage_dir=tmp_path / "storage")

    inv = Investigation(
        investigation_id="inv-rev-01",
        title="Review Test Case",
        objective="Verify suspect movement",
        scope_description="Gate camera",
        media_asset_ids=["media-01"],
    )
    repo.add_investigation(inv)
    now = datetime.now(UTC)
    state = InvestigationState(
        investigation_id="inv-rev-01",
        status=InvestigationStatus.COMPLETED,
        completed_at=now,
        event_ids=["evt-01"],
    )
    repo.save_state(state)

    event = Event(
        event_id="evt-01",
        event_type="fence_crossing",
        description="Possible fence crossing detected.",
        observation_ids=["obs-01"],
        status="proposed",
    )
    repo.add_event(event)

    # 1. Review event -> confirmed
    updated_evt, audit_entry = service.review_event(
        investigation_id="inv-rev-01",
        event_id="evt-01",
        status="confirmed",
        reviewer="detective-reese",
        notes="Confirmed breach by intruder wearing dark hoodie.",
        description="Confirmed south perimeter breach.",
    )

    assert updated_evt.status == "confirmed"
    assert updated_evt.reviewer == "detective-reese"
    assert updated_evt.review_notes == "Confirmed breach by intruder wearing dark hoodie."
    assert updated_evt.description == "Confirmed south perimeter breach."
    assert updated_evt.reviewed_at is not None

    assert audit_entry.action == "event_review"
    assert audit_entry.actor == "detective-reese"
    assert audit_entry.changes["status"]["old"] == "proposed"
    assert audit_entry.changes["status"]["new"] == "confirmed"

    # 2. Check audit log query
    logs = service.get_audit_logs("inv-rev-01")
    assert len(logs) == 1
    assert logs[0].audit_id == audit_entry.audit_id

    service.shutdown(wait=False)


def test_edit_event_workflow(tmp_path: Path) -> None:
    repo = SqliteInvestigationRepository(":memory:")
    service = InvestigationService(repository=repo, storage_dir=tmp_path / "storage")

    inv = Investigation(
        investigation_id="inv-rev-02",
        title="Edit Test Case",
        objective="Test event attribute edits",
        scope_description="Camera 1",
        media_asset_ids=["media-01"],
    )
    repo.add_investigation(inv)
    event = Event(
        event_id="evt-02",
        event_type="vehicle_entry",
        description="White sedan arrives.",
        observation_ids=["obs-02"],
        status="proposed",
    )
    repo.add_event(event)

    updated_evt, audit_entry = service.edit_event(
        investigation_id="inv-rev-02",
        event_id="evt-02",
        editor="analyst-finch",
        updates={"description": "White sedan with license plate 7XYZ89 arrives.", "start_seconds": 15.0, "end_seconds": 22.0},
        notes="Refined license plate details from high-res frame.",
    )

    assert updated_evt.description == "White sedan with license plate 7XYZ89 arrives."
    assert updated_evt.start_seconds == 15.0
    assert updated_evt.end_seconds == 22.0
    assert audit_entry.action == "event_edit"
    assert audit_entry.actor == "analyst-finch"

    service.shutdown(wait=False)


def test_finalize_report_workflow_with_clip_slicing(tmp_path: Path) -> None:
    repo = SqliteInvestigationRepository(":memory:")
    service = InvestigationService(repository=repo, storage_dir=tmp_path / "storage")

    # Create real video for slicing
    video_path = tmp_path / "finalize_test.mp4"
    create_test_video(video_path, duration_seconds=3.0, fps=24)

    media_asset = MediaAsset(
        media_asset_id="media-fin-01",
        media_type="video",
        storage_uri=video_path.as_uri(),
        duration_seconds=3.0,
    )
    repo.add_media_asset(media_asset)

    inv = Investigation(
        investigation_id="inv-fin-01",
        title="Finalize Test Case",
        objective="Verify incident finalization and clip generation",
        scope_description="Test scope",
        media_asset_ids=["media-fin-01"],
    )
    repo.add_investigation(inv)

    event = Event(
        event_id="evt-fin-01",
        event_type="unauthorized_access",
        description="Intruder opens secured door.",
        observation_ids=["obs-fin-01"],
        status="confirmed",
        start_seconds=0.5,
        end_seconds=2.0,
        reviewer="lead-investigator",
    )
    repo.add_event(event)

    now = datetime.now(UTC)
    state = InvestigationState(
        investigation_id="inv-fin-01",
        status=InvestigationStatus.COMPLETED,
        completed_at=now,
        event_ids=["evt-fin-01"],
        observation_ids=["obs-fin-01"],
    )
    repo.save_state(state)

    # Finalize report
    final_report, audit_entry = service.finalize_report(
        investigation_id="inv-fin-01",
        finalized_by="detective-carter",
        notes="Final case wrap-up for prosecution.",
        auto_slice_clips=True,
    )

    assert final_report.version == 1
    assert final_report.status == "finalized"
    assert final_report.finalized_by == "detective-carter"
    assert final_report.finalized_at is not None
    assert len(final_report.clip_artifact_ids) > 0

    # Ensure clip was created and stored in repository
    clip_art = repo.get_artifact(final_report.clip_artifact_ids[0])
    assert clip_art.artifact_type == "clip"
    assert clip_art.source_reference.media_asset_id == "media-fin-01"

    # Check audit log
    assert audit_entry.action == "report_finalize"
    assert audit_entry.actor == "detective-carter"
    assert audit_entry.target_id == final_report.report_id

    service.shutdown(wait=False)
