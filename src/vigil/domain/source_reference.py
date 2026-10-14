"""Source evidence reference schema."""

from datetime import datetime
import math

from pydantic import Field, field_validator, model_validator

from vigil.domain.base import DomainModel


class SourceReference(DomainModel):
    """Identifies a precise interval in an original media asset."""

    media_asset_id: str = Field(
        min_length=1,
        description="ID of the original media containing the evidence.",
    )

    start_seconds: float = Field(
        ge=0,
        description=(
            "Inclusive start position in seconds on the original "
            "media timeline."
        ),
    )

    end_seconds: float = Field(
        gt=0,
        description=(
            "Exclusive end position in seconds on the original "
            "media timeline."
        ),
    )

    source_timestamp: datetime | None = Field(
        default=None,
        description=(
            "Optional timezone-aware wall-clock timestamp corresponding "
            "to start_seconds; retain its timezone or normalize to UTC."
        ),
    )

    @field_validator("start_seconds", "end_seconds")
    @classmethod
    def validate_finite_time(cls, value: float) -> float:
        """Reject NaN and infinite timeline positions."""
        if not math.isfinite(value):
            raise ValueError("Timeline positions must be finite.")
        return value

    @field_validator("source_timestamp")
    @classmethod
    def validate_source_timestamp(
        cls, value: datetime | None
    ) -> datetime | None:
        """Require timezone information when wall-clock time is known."""
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("Source timestamp must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def validate_interval(self) -> "SourceReference":
        """Require a positive-length interval."""
        if self.end_seconds <= self.start_seconds:
            raise ValueError("End time must be greater than start time.")
        return self