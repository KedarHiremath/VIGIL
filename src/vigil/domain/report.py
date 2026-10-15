"""Domain schema for investigation reports."""

from datetime import UTC, datetime

from pydantic import Field, field_validator

from vigil.domain.base import DomainModel


class Report(DomainModel):
    """Structured findings with references to supporting evidence."""

    report_id: str = Field(min_length=1)
    investigation_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)

    observation_ids: list[str] = Field(default_factory=list)
    event_ids: list[str] = Field(default_factory=list)
    assessment_ids: list[str] = Field(default_factory=list)
    coverage_ids: list[str] = Field(default_factory=list)

    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    generated_by: str = Field(min_length=1)

    @field_validator(
        "report_id",
        "investigation_id",
        "title",
        "summary",
        "generated_by",
    )
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        """Reject blank required text fields."""
        if not value.strip():
            raise ValueError("Value must not be blank")
        return value

    @field_validator(
        "observation_ids",
        "event_ids",
        "assessment_ids",
        "coverage_ids",
    )
    @classmethod
    def validate_unique_references(cls, values: list[str]) -> list[str]:
        """Require unique, nonblank references."""
        if any(not value.strip() for value in values):
            raise ValueError("Reference IDs must not be blank")
        if len(values) != len(set(values)):
            raise ValueError("Reference IDs must be unique")
        return values

    @field_validator("generated_at")
    @classmethod
    def require_timezone_aware_generated_at(cls, value: datetime) -> datetime:
        """Require a timezone-aware generation timestamp."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        return value
