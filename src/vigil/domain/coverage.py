"""Domain schema for investigation coverage."""
from datetime import datetime
from enum import Enum

from pydantic import Field, field_validator, model_validator

from vigil.domain.base import DomainModel


class CoverageStatus(str, Enum):
    """Outcome of examining a source or time interval."""

    EXAMINED = "examined"
    PARTIAL = "partial"
    FAILED = "failed"
    NOT_EXAMINED = "not_examined"


class CoverageRecord(DomainModel):
    """Records the examination status of a source or interval."""

    coverage_id: str = Field(min_length=1)
    investigation_id: str = Field(min_length=1)
    source_reference_id: str = Field(min_length=1)

    status: CoverageStatus

    interval_start: datetime | None = None
    interval_end: datetime | None = None
    examined_at: datetime | None = None

    notes: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)

    @field_validator(
        "coverage_id",
        "investigation_id",
        "source_reference_id",
    )
    @classmethod
    def reject_blank_identifiers(cls, value: str) -> str:
        """Reject blank identifiers."""
        if not value.strip():
            raise ValueError("Identifier must not be blank")
        return value

    @field_validator("notes")
    @classmethod
    def reject_blank_notes(
        cls, value: str | None
    ) -> str | None:
        """Reject blank notes when supplied."""
        if value is not None and not value.strip():
            raise ValueError("notes must not be blank")
        return value

    @field_validator("artifact_ids")
    @classmethod
    def validate_artifact_ids(
        cls, values: list[str]
    ) -> list[str]:
        """Require unique, nonblank artifact IDs."""
        if any(not value.strip() for value in values):
            raise ValueError("Artifact IDs must not be blank")
        if len(values) != len(set(values)):
            raise ValueError("Artifact IDs must be unique")
        return values

    @field_validator(
        "interval_start",
        "interval_end",
        "examined_at",
    )
    @classmethod
    def require_timezone_aware_timestamps(
        cls, value: datetime | None
    ) -> datetime | None:
        """Require timezone-aware timestamps when supplied."""
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("Timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_interval_and_status(self) -> "CoverageRecord":
        """Validate interval order and examination timestamps."""
        if (self.interval_start is None) != (
            self.interval_end is None
        ):
            raise ValueError(
                "interval_start and interval_end must be "
                "provided together"
            )

        if (
            self.interval_start is not None
            and self.interval_end is not None
            and self.interval_end < self.interval_start
        ):
            raise ValueError(
                "interval_end must not precede interval_start"
            )

        if (
            self.status == CoverageStatus.EXAMINED
            and self.examined_at is None
        ):
            raise ValueError(
                "examined status requires examined_at"
            )

        return self