"""Domain schema for investigation reports."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from vigil.domain.base import DomainModel
from vigil.domain.common import Identifier, ReferenceIds, Timestamp


class Report(DomainModel):
    """Structured findings with references to supporting evidence."""

    report_id: Identifier = Field(min_length=1)
    investigation_id: Identifier = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)

    observation_ids: ReferenceIds = Field(default_factory=list)
    event_ids: ReferenceIds = Field(default_factory=list)
    assessment_ids: ReferenceIds = Field(default_factory=list)
    coverage_ids: ReferenceIds = Field(default_factory=list)

    version: int = Field(
        default=1,
        ge=1,
        description="Sequential version number of the report.",
    )
    status: Literal["draft", "in_review", "finalized"] = Field(
        default="draft",
        description="Review and finalization status of the report.",
    )
    clip_artifact_ids: ReferenceIds = Field(
        default_factory=list,
        description="Artifact IDs for playable incident sub-clips embedded in the report.",
    )
    evidence_frame_artifact_ids: ReferenceIds = Field(
        default_factory=list,
        description="Artifact IDs for selected incident frames embedded in the report.",
    )
    visual_evidence: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Structured visual evidence items containing frame refs, captions, tags, and annotations.",
    )
    notes: str | None = Field(
        default=None,
        description="Investigator comments, review rationale, or closing remarks.",
    )
    finalized_at: Timestamp | None = Field(
        default=None,
        description="Timestamp when report was formally finalized.",
    )
    finalized_by: str | None = Field(
        default=None,
        description="Investigator username/badge who finalized the report.",
    )

    generated_at: Timestamp = Field(default_factory=lambda: datetime.now(UTC))
    generated_by: str = Field(min_length=1)

    @field_validator("title", "summary", "generated_by")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        """Reject blank required text fields."""
        if not value.strip():
            raise ValueError("Value must not be blank")
        return value
