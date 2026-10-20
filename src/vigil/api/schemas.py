"""Pydantic schemas for the VIGIL REST and WebSocket API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from vigil.domain.audit import AuditLog
from vigil.domain.event import Event
from vigil.domain.report import Report


class InvestigationCreateResponse(BaseModel):
    """Response returned upon successfully creating/initiating an investigation."""

    investigation_id: str = Field(description="Unique investigation ID")
    title: str = Field(description="Investigation title")
    status: str = Field(description="Current status (e.g. 'created', 'running')")
    media_asset_id: str = Field(description="Primary ingested media asset ID")
    camera_id: str | None = Field(
        default=None, description="Registered camera ID if any"
    )
    frame_count: int = Field(
        default=0, description="Number of sample frames extracted"
    )
    has_audio: bool = Field(
        default=False, description="Whether an audio stream was extracted"
    )
    message: str = Field(description="Informational status message")


class InvestigationStatusResponse(BaseModel):
    """Detailed status response for investigation polling."""

    investigation_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    completed_tasks: int
    task_ids: list[str] = Field(default_factory=list)
    observation_count: int
    event_count: int
    coverage_count: int
    has_report: bool
    report_id: str | None = None
    error: str | None = None


class InvestigationSummaryResponse(BaseModel):
    """Summary item for listing investigations."""

    investigation_id: str
    title: str
    objective: str
    status: str
    created_at: datetime
    media_asset_ids: list[str] = Field(default_factory=list)


class TelemetryEventMessage(BaseModel):
    """WebSocket event envelope for real-time telemetry."""

    investigation_id: str
    event_type: str
    timestamp: str
    data: dict[str, Any]


# -------------------------------------------------------------------------
# Phase 5: Human Review & Audit Schemas
# -------------------------------------------------------------------------


class EventReviewRequest(BaseModel):
    """Request payload for an investigator reviewing a proposed event."""

    status: Literal["confirmed", "rejected", "under_review", "proposed"] = (
        Field(
            description="Decision status: confirmed (verified), rejected (dismissed), or under_review"
        )
    )
    reviewer: str = Field(
        min_length=1,
        description="Investigator username, badge number, or reviewer identifier",
    )
    notes: str | None = Field(
        default=None,
        description="Forensic rationale, corroborating evidence notes, or justification",
    )
    description: str | None = Field(
        default=None,
        description="Optional edited human-readable event description",
    )
    event_type: str | None = Field(
        default=None,
        description="Optional edited category classification",
    )
    start_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Optional footage-relative start offset in seconds",
    )
    end_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Optional footage-relative end offset in seconds",
    )
    start_time: datetime | None = Field(
        default=None,
        description="Optional wall-clock start datetime",
    )
    end_time: datetime | None = Field(
        default=None,
        description="Optional wall-clock end datetime",
    )


class EventReviewResponse(BaseModel):
    """Response returned upon successfully reviewing or modifying an event."""

    event: Event = Field(description="Updated Event domain model")
    audit_log: AuditLog = Field(
        description="Immutable audit log entry tracking the decision"
    )
    message: str = Field(description="Status confirmation message")


class EventEditRequest(BaseModel):
    """Request payload for direct investigator edits to an event record."""

    editor: str = Field(
        min_length=1,
        description="Investigator badge or username applying the edits",
    )
    description: str | None = None
    event_type: str | None = None
    start_seconds: float | None = Field(default=None, ge=0.0)
    end_seconds: float | None = Field(default=None, ge=0.0)
    start_time: datetime | None = None
    end_time: datetime | None = None
    notes: str | None = Field(
        default=None,
        description="Investigator notes explaining the edit",
    )


class ReportFinalizeRequest(BaseModel):
    """Request payload for finalizing a report and locking evidence findings."""

    finalized_by: str = Field(
        min_length=1,
        description="Lead investigator username or badge number finalizing the investigation",
    )
    title: str | None = Field(
        default=None,
        description="Optional customized title for the finalized report deliverable",
    )
    summary: str | None = Field(
        default=None,
        description="Optional finalized executive summary incorporating human review insights",
    )
    notes: str | None = Field(
        default=None,
        description="Concluding forensic notes, legal remarks, or chain of custody sign-off",
    )
    auto_slice_clips: bool = Field(
        default=True,
        description="Whether to automatically slice playable video sub-clips for confirmed incidents",
    )


class ReportFinalizeResponse(BaseModel):
    """Response returned upon successfully finalizing an investigation report."""

    report: Report = Field(description="Finalized Report domain model")
    audit_log: AuditLog = Field(
        description="Audit entry recording the report finalization"
    )
    version: int = Field(description="Report version number")
    clip_count: int = Field(
        description="Number of incident clips linked in report"
    )
    message: str = Field(description="Confirmation message")


class IncidentClipSliceRequest(BaseModel):
    """Request payload for cutting a sub-clip for an event."""

    padding_seconds: float = Field(
        default=1.0,
        ge=0.0,
        description="Padding in seconds added before start and after end",
    )
