
"""Domain schema for investigation reports."""

from datetime import UTC, datetime

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

    generated_at: Timestamp = Field(default_factory=lambda: datetime.now(UTC))
    generated_by: str = Field(min_length=1)

    @field_validator("title", "summary", "generated_by")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        """Reject blank required text fields."""
        if not value.strip():
            raise ValueError("Value must not be blank")
        return value
