"""Unit tests for Phase 5 AuditLog, Event review fields, and Report versioning domain schemas."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from vigil.domain.audit import AuditLog
from vigil.domain.event import Event
from vigil.domain.report import Report


def test_audit_log_valid_creation() -> None:
    now = datetime.now(UTC)
    log = AuditLog(
        audit_id="audit-001",
        investigation_id="inv-001",
        action="event_review",
        actor="investigator-alice",
        timestamp=now,
        target_type="event",
        target_id="evt-001",
        changes={"status": {"old": "proposed", "new": "confirmed"}},
        notes="Verified suspect match on gate camera.",
        metadata={"camera_id": "cam-gate-01"},
    )

    assert log.audit_id == "audit-001"
    assert log.investigation_id == "inv-001"
    assert log.action == "event_review"
    assert log.actor == "investigator-alice"
    assert log.timestamp == now
    assert log.target_type == "event"
    assert log.target_id == "evt-001"
    assert log.changes["status"]["new"] == "confirmed"
    assert log.notes == "Verified suspect match on gate camera."


def test_audit_log_rejects_blank_actor() -> None:
    with pytest.raises(ValidationError):
        AuditLog(
            audit_id="audit-002",
            investigation_id="inv-001",
            action="event_review",
            actor="   ",
            target_type="event",
            target_id="evt-001",
        )


def test_audit_log_immutability() -> None:
    log = AuditLog(
        audit_id="audit-003",
        investigation_id="inv-001",
        action="event_review",
        actor="investigator-bob",
        target_type="event",
        target_id="evt-001",
    )
    with pytest.raises(ValidationError):
        log.actor = "someone-else"  # type: ignore[misc]


def test_event_with_review_and_seconds_fields() -> None:
    now = datetime.now(UTC)
    event = Event(
        event_id="evt-001",
        event_type="perimeter_breach",
        description="Individual climbs south perimeter fence.",
        observation_ids=["obs-001"],
        status="confirmed",
        start_seconds=12.5,
        end_seconds=18.0,
        reviewer="badge-4402",
        review_notes="Clear footage, verified breach.",
        reviewed_at=now,
    )

    assert event.status == "confirmed"
    assert event.start_seconds == 12.5
    assert event.end_seconds == 18.0
    assert event.reviewer == "badge-4402"
    assert event.review_notes == "Clear footage, verified breach."
    assert event.reviewed_at == now


def test_event_rejects_reversed_seconds() -> None:
    with pytest.raises(ValidationError, match="Event end seconds cannot precede start seconds"):
        Event(
            event_id="evt-002",
            event_type="entry",
            description="Reversed test",
            observation_ids=["obs-001"],
            start_seconds=20.0,
            end_seconds=10.0,
        )


def test_report_versioning_and_finalization_fields() -> None:
    now = datetime.now(UTC)
    report = Report(
        report_id="rep-001",
        investigation_id="inv-001",
        title="Final Forensic Report",
        summary="Detailed incident report.",
        generated_by="investigator-lead",
        version=2,
        status="finalized",
        clip_artifact_ids=["clip-001", "clip-002"],
        notes="All findings verified and court-ready.",
        finalized_at=now,
        finalized_by="lead-detective-carter",
    )

    assert report.version == 2
    assert report.status == "finalized"
    assert report.clip_artifact_ids == ["clip-001", "clip-002"]
    assert report.notes == "All findings verified and court-ready."
    assert report.finalized_at == now
    assert report.finalized_by == "lead-detective-carter"
