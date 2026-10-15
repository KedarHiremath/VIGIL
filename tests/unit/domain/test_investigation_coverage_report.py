"""Tests for investigation, coverage, and report schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from vigil.domain.coverage import CoverageRecord, CoverageStatus
from vigil.domain.investigation import Investigation
from vigil.domain.report import Report


def test_investigation_accepts_valid_inputs() -> None:
    investigation = Investigation(
        investigation_id="inv-001",
        title="Warehouse review",
        objective="Establish the sequence of events",
        scope_description="Review the north entrance camera",
        media_asset_ids=["media-001"],
        source_reference_ids=["source-001"],
    )

    assert investigation.investigation_id == "inv-001"
    assert investigation.media_asset_ids == ["media-001"]


def test_investigation_rejects_duplicate_media_ids() -> None:
    with pytest.raises(ValidationError):
        Investigation(
            investigation_id="inv-001",
            title="Warehouse review",
            objective="Establish the sequence",
            scope_description="North entrance",
            media_asset_ids=["media-001", "media-001"],
        )


def test_investigation_rejects_naive_created_at() -> None:
    with pytest.raises(ValidationError):
        Investigation(
            investigation_id="inv-001",
            title="Warehouse review",
            objective="Establish the sequence",
            scope_description="North entrance",
            created_at=datetime(2026, 10, 15, 9, 0),
        )


def test_investigation_rejects_blank_objective() -> None:
    with pytest.raises(ValidationError):
        Investigation(
            investigation_id="inv-001",
            title="Warehouse review",
            objective="   ",
            scope_description="North entrance",
        )


def test_coverage_accepts_examined_source() -> None:
    record = CoverageRecord(
        coverage_id="cov-001",
        investigation_id="inv-001",
        source_reference_id="source-001",
        status=CoverageStatus.EXAMINED,
        interval_start=datetime(2026, 10, 15, 9, 0, tzinfo=UTC),
        interval_end=datetime(2026, 10, 15, 10, 0, tzinfo=UTC),
        examined_at=datetime(2026, 10, 15, 10, 5, tzinfo=UTC),
        artifact_ids=["artifact-001"],
    )

    assert record.status == CoverageStatus.EXAMINED
    assert record.artifact_ids == ["artifact-001"]


def test_coverage_rejects_examined_without_timestamp() -> None:
    with pytest.raises(ValidationError):
        CoverageRecord(
            coverage_id="cov-001",
            investigation_id="inv-001",
            source_reference_id="source-001",
            status=CoverageStatus.EXAMINED,
        )


def test_coverage_allows_failed_without_examined_at() -> None:
    record = CoverageRecord(
        coverage_id="cov-002",
        investigation_id="inv-001",
        source_reference_id="source-002",
        status=CoverageStatus.FAILED,
        notes="Source could not be decoded",
    )

    assert record.status == CoverageStatus.FAILED


def test_coverage_rejects_reversed_interval() -> None:
    with pytest.raises(ValidationError):
        CoverageRecord(
            coverage_id="cov-003",
            investigation_id="inv-001",
            source_reference_id="source-001",
            status=CoverageStatus.PARTIAL,
            interval_start=datetime(2026, 10, 15, 11, 0, tzinfo=UTC),
            interval_end=datetime(2026, 10, 15, 10, 0, tzinfo=UTC),
        )


def test_coverage_requires_both_interval_endpoints() -> None:
    with pytest.raises(ValidationError):
        CoverageRecord(
            coverage_id="cov-004",
            investigation_id="inv-001",
            source_reference_id="source-001",
            status=CoverageStatus.PARTIAL,
            interval_start=datetime(2026, 10, 15, 9, 0, tzinfo=UTC),
        )


def test_coverage_rejects_duplicate_artifact_ids() -> None:
    with pytest.raises(ValidationError):
        CoverageRecord(
            coverage_id="cov-005",
            investigation_id="inv-001",
            source_reference_id="source-001",
            status=CoverageStatus.PARTIAL,
            artifact_ids=["artifact-001", "artifact-001"],
        )


def test_report_accepts_valid_evidence_references() -> None:
    report = Report(
        report_id="report-001",
        investigation_id="inv-001",
        title="Investigation findings",
        summary="Two events require further review.",
        observation_ids=["obs-001"],
        event_ids=["event-001"],
        assessment_ids=["assessment-001"],
        coverage_ids=["cov-001"],
        generated_by="report-builder",
    )

    assert report.event_ids == ["event-001"]
    assert report.coverage_ids == ["cov-001"]


def test_report_rejects_duplicate_observation_ids() -> None:
    with pytest.raises(ValidationError):
        Report(
            report_id="report-001",
            investigation_id="inv-001",
            title="Investigation findings",
            summary="Findings summary",
            observation_ids=["obs-001", "obs-001"],
            generated_by="report-builder",
        )


def test_report_rejects_naive_generated_at() -> None:
    with pytest.raises(ValidationError):
        Report(
            report_id="report-001",
            investigation_id="inv-001",
            title="Investigation findings",
            summary="Findings summary",
            generated_by="report-builder",
            generated_at=datetime(2026, 10, 15, 10, 0),
        )


def test_report_rejects_blank_summary() -> None:
    with pytest.raises(ValidationError):
        Report(
            report_id="report-001",
            investigation_id="inv-001",
            title="Investigation findings",
            summary="   ",
            generated_by="report-builder",
        )


def test_investigation_normalizes_shared_identifiers() -> None:
    investigation = Investigation(
        investigation_id=" inv-001 ",
        title="Security review",
        objective="Review source footage",
        scope_description="Main entrance",
        media_asset_ids=[" media-001 "],
    )

    assert investigation.investigation_id == "inv-001"
    assert investigation.media_asset_ids == ["media-001"]


def test_investigation_rejects_duplicate_references_after_normalization() -> None:
    with pytest.raises(ValidationError):
        Investigation(
            investigation_id="inv-001",
            title="Security review",
            objective="Review source footage",
            scope_description="Main entrance",
            media_asset_ids=["media-001", " media-001 "],
        )


def test_coverage_rejects_naive_timestamps() -> None:
    with pytest.raises(ValidationError):
        CoverageRecord(
            coverage_id="coverage-001",
            investigation_id="inv-001",
            source_reference_id="source-001",
            status=CoverageStatus.PARTIAL,
            examined_at=datetime(2026, 10, 15, 9, 0),
        )


def test_coverage_rejects_duplicate_artifact_ids_after_normalization() -> None:
    with pytest.raises(ValidationError):
        CoverageRecord(
            coverage_id="coverage-001",
            investigation_id="inv-001",
            source_reference_id="source-001",
            status=CoverageStatus.PARTIAL,
            artifact_ids=["artifact-001", " artifact-001 "],
        )


def test_report_normalizes_shared_identifiers_and_references() -> None:
    report = Report(
        report_id=" report-001 ",
        investigation_id=" inv-001 ",
        title="Investigation report",
        summary="Summary of findings",
        observation_ids=[" obs-001 "],
        generated_by="report-generator",
    )

    assert report.report_id == "report-001"
    assert report.investigation_id == "inv-001"
    assert report.observation_ids == ["obs-001"]


def test_report_rejects_duplicate_references_after_normalization() -> None:
    with pytest.raises(ValidationError):
        Report(
            report_id="report-001",
            investigation_id="inv-001",
            title="Investigation report",
            summary="Summary of findings",
            observation_ids=["obs-001", " obs-001 "],
            generated_by="report-generator",
        )
