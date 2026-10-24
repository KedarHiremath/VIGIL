"""Unit tests for ReportExporter HTML and PDF export."""

from __future__ import annotations

from datetime import UTC, datetime

from vigil.domain.artifact import Artifact
from vigil.domain.audit import AuditLog
from vigil.domain.coverage import CoverageRecord, CoverageStatus
from vigil.domain.event import Event
from vigil.domain.evidence_assessment import EvidenceAssessment
from vigil.domain.investigation import Investigation
from vigil.domain.media_asset import MediaAsset
from vigil.domain.observation import Observation
from vigil.domain.provenance import Provenance
from vigil.domain.report import Report
from vigil.domain.source_reference import SourceReference
from vigil.services.exporter import ReportExporter


def test_export_html_contains_required_sections() -> None:
    now = datetime(2026, 10, 20, 14, 0, tzinfo=UTC)
    inv = Investigation(
        investigation_id="inv-exp-01",
        title="HTML Export Case",
        objective="Determine timeline of warehouse breach",
        scope_description="South gate",
        media_asset_ids=["media-exp-01"],
    )
    report = Report(
        report_id="rep-exp-01",
        investigation_id="inv-exp-01",
        title="Forensic Analysis Report - Warehouse Breach",
        summary="Comprehensive forensic examination confirmed perimeter breach at 00:15.",
        generated_by="vigil-agent",
        version=2,
        status="finalized",
        finalized_by="detective-shaw",
        finalized_at=now,
    )
    events = [
        Event(
            event_id="evt-01",
            event_type="perimeter_breach",
            description="Fence cut on south perimeter.",
            observation_ids=["obs-01"],
            status="confirmed",
            start_seconds=10.0,
            end_seconds=15.0,
            reviewer="detective-shaw",
            review_notes="Tool visible in frame.",
        ),
        Event(
            event_id="evt-02",
            event_type="false_alarm",
            description="Motion trigger near trash bin.",
            observation_ids=["obs-02"],
            status="rejected",
            reviewer="detective-shaw",
            review_notes="Stray cat triggered motion sensor.",
        ),
    ]
    observations = [
        Observation(
            observation_id="obs-01",
            modality="video",
            observation_type="fence_breach",
            description="Person cutting chain-link fence.",
            source_references=[
                SourceReference(media_asset_id="media-exp-01", start_seconds=10.0, end_seconds=15.0)
            ],
            provenance=Provenance(
                producer_type="vision_model",
                producer_name="vigil-vision",
                method="detection",
            ),
        ),
    ]
    assessments = [
        EvidenceAssessment(
            assessment_id="ass-01",
            target_type="event",
            target_id="evt-01",
            assessment_type="support_level",
            rating="high",
            rationale="Corroborated by high-contrast night vision frames.",
            assessed_by="evidence-agent",
        )
    ]
    coverages = [
        CoverageRecord(
            coverage_id="cov-01",
            investigation_id="inv-exp-01",
            source_reference_id="sr-01",
            status=CoverageStatus.EXAMINED,
            examined_at=now,
        )
    ]
    artifacts = [
        Artifact(
            artifact_id="clip-exp-01",
            artifact_type="clip",
            media_type="video",
            storage_uri="file:///storage/clips/clip_01.mp4",
            source_reference=SourceReference(
                media_asset_id="media-exp-01", start_seconds=10.0, end_seconds=15.0
            ),
            sha256="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
        )
    ]
    audit_logs = [
        AuditLog(
            audit_id="audit-exp-01",
            investigation_id="inv-exp-01",
            action="event_review",
            actor="detective-shaw",
            timestamp=now,
            target_type="event",
            target_id="evt-01",
            changes={"status": {"old": "proposed", "new": "confirmed"}},
            notes="Confirmed via physical inspection of fence.",
        )
    ]
    media_assets = [
        MediaAsset(
            media_asset_id="media-exp-01",
            media_type="video",
            storage_uri="file:///storage/raw/feed.mp4",
            sha256="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        )
    ]

    html_out = ReportExporter.export_html(
        investigation=inv,
        report=report,
        events=events,
        observations=observations,
        assessments=assessments,
        coverages=coverages,
        artifacts=artifacts,
        audit_logs=audit_logs,
        media_assets=media_assets,
    )

    assert "<!DOCTYPE html>" in html_out
    assert "Forensic Analysis Report - Warehouse Breach" in html_out
    assert "Executive Summary" in html_out
    assert "perimeter_breach" in html_out or "Perimeter Breach" in html_out
    assert "CONFIRMED" in html_out
    assert "REJECTED" in html_out
    assert "<video" in html_out
    assert "clip-exp-01" in html_out
    assert "detective-shaw" in html_out
    assert "audit-exp-01" in html_out or "event_review" in html_out


def test_export_pdf_generates_valid_pdf_document() -> None:
    now = datetime(2026, 10, 20, 15, 0, tzinfo=UTC)
    inv = Investigation(
        investigation_id="inv-pdf-01",
        title="PDF Export Verification",
        objective="Verify publication quality PDF compilation",
        scope_description="Camera 01",
        media_asset_ids=["media-pdf-01"],
    )
    report = Report(
        report_id="rep-pdf-01",
        investigation_id="inv-pdf-01",
        title="Formal Forensic Investigation Report",
        summary="Automated multi-agent timeline correlation completed with evidence verification.",
        generated_by="vigil-system",
        version=1,
        status="finalized",
        finalized_by="chief-inspector-morse",
        finalized_at=now,
    )
    events = [
        Event(
            event_id="evt-p1",
            event_type="suspicious_loitering",
            description="Individual remains stationary near emergency exit.",
            observation_ids=["obs-p1"],
            status="confirmed",
            start_seconds=4.0,
            end_seconds=9.5,
            reviewer="chief-inspector-morse",
            review_notes="Subject observed looking at surveillance cameras.",
        )
    ]
    artifacts = [
        Artifact(
            artifact_id="clip-p1",
            artifact_type="clip",
            media_type="video",
            storage_uri="file:///storage/clips/clip_p1.mp4",
            source_reference=SourceReference(
                media_asset_id="media-pdf-01", start_seconds=4.0, end_seconds=9.5
            ),
            sha256="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        )
    ]
    audit_logs = [
        AuditLog(
            audit_id="audit-p1",
            investigation_id="inv-pdf-01",
            action="report_finalize",
            actor="chief-inspector-morse",
            timestamp=now,
            target_type="report",
            target_id="rep-pdf-01",
            notes="Ready for submission.",
        )
    ]
    media_assets = [
        MediaAsset(
            media_asset_id="media-pdf-01",
            media_type="video",
            storage_uri="file:///storage/source.mp4",
            sha256="0000000000000000000000000000000000000000000000000000000000000000",
        )
    ]

    pdf_bytes = ReportExporter.export_pdf(
        investigation=inv,
        report=report,
        events=events,
        observations=[],
        assessments=[],
        coverages=[],
        artifacts=artifacts,
        audit_logs=audit_logs,
        media_assets=media_assets,
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")
