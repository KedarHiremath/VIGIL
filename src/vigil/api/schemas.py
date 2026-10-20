"""Pydantic schemas for the VIGIL REST and WebSocket API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class InvestigationCreateResponse(BaseModel):
    """Response returned upon successfully creating/initiating an investigation."""

    investigation_id: str = Field(description="Unique investigation ID")
    title: str = Field(description="Investigation title")
    status: str = Field(description="Current status (e.g. 'created', 'running')")
    media_asset_id: str = Field(description="Primary ingested media asset ID")
    camera_id: str | None = Field(default=None, description="Registered camera ID if any")
    frame_count: int = Field(default=0, description="Number of sample frames extracted")
    has_audio: bool = Field(default=False, description="Whether an audio stream was extracted")
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
