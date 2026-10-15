"""Domain schema for investigation coverage."""

from enum import Enum

from pydantic import Field, field_validator, model_validator

from vigil.domain.base import DomainModel
from vigil.domain.common import Identifier, ReferenceIds, Timestamp


class CoverageStatus(str, Enum):
    """Outcome of examining a source or time interval."""

    EXAMINED = "examined"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_EXAMINED = "not_examined"


class CoverageRecord(DomainModel):
    """Records the examination status of a source or interval."""

    coverage_id: Identifier = Field(min_length=1)
    investigation_id: Identifier = Field(min_length=1)
    source_reference_id: Identifier = Field(min_length=1)

    status: CoverageStatus

    interval_start: Timestamp | None = None
    interval_end: Timestamp | None = None
    examined_at: Timestamp | None = None

    notes: str | None = None
    artifact_ids: ReferenceIds = Field(default_factory=list)

    @field_validator("notes")
    @classmethod
    def reject_blank_notes(cls, value: str | None) -> str | None:
        """Reject blank notes when supplied."""
        if value is not None and not value.strip():
            raise ValueError("notes must not be blank")
        return value

    @model_validator(mode="after")
    def validate_interval_and_status(self) -> "CoverageRecord":
        """Validate interval order and examination timestamps."""
        if (self.interval_start is None) != (self.interval_end is None):
            raise ValueError(
                "interval_start and interval_end must be provided together"
            )

        if (
            self.interval_start is not None
            and self.interval_end is not None
            and self.interval_end < self.interval_start
        ):
            raise ValueError("interval_end must not precede interval_start")

        if self.status == CoverageStatus.EXAMINED and self.examined_at is None:
            raise ValueError("examined status requires examined_at")

        return self
