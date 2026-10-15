"""Source evidence reference schema."""

import math

from pydantic import Field, field_validator, model_validator

from vigil.domain.base import DomainModel
from vigil.domain.common import Identifier, Timestamp


class SourceReference(DomainModel):
    """Identifies a precise interval in an original media asset."""

    media_asset_id: Identifier = Field(
        description="ID of the original media containing the evidence.",
    )

    start_seconds: float = Field(
        ge=0,
        description=(
            "Inclusive start position in seconds on the original media timeline."
        ),
    )

    end_seconds: float = Field(
        gt=0,
        description=(
            "Exclusive end position in seconds on the original media timeline."
        ),
    )

    source_timestamp: Timestamp | None = Field(
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

    @model_validator(mode="after")
    def validate_interval(self) -> "SourceReference":
        """Require a positive-length half-open interval."""
        if self.end_seconds <= self.start_seconds:
            raise ValueError("End time must be greater than start time.")
        return self