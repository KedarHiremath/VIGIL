"""Relationship schema between investigation events."""

import math
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from vigil.domain.base import DomainModel


class EventLink(DomainModel):
    """Represents a typed relationship between two distinct events."""

    event_link_id: str = Field(
        min_length=1,
        description="Stable unique identifier for this relationship."
    )

    from_event_id: str = Field(
        min_length=1,
        description="ID of the source event in the relationship."
    )

    to_event_id: str = Field(
        min_length=1,
        description="ID of the destination event in the relationship."
    )

    relationship_type: Literal[
        "before",
        "after",
        "overlaps",
        "related_to",
        "possible_same_incident",
    ] = Field(
        description="Type of relationship between the two events."
    )

    rationale: str = Field(
        min_length=1,
        description="Explanation for recording this relationship."
    )

    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description=(
            "Optional producer-reported confidence score; "
            "not necessarily a calibrated probability."
        )
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timezone-aware time when the relationship was recorded."
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence(
        cls, value: float | None
    ) -> float | None:
        """Reject non-finite confidence values."""
        if value is not None and not math.isfinite(value):
            raise ValueError("Confidence must be finite.")
        return value

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        """Require a timezone-aware creation timestamp."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Creation timestamp must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def validate_distinct_events(self) -> "EventLink":
        """Prevent an event from being linked to itself."""
        if self.from_event_id == self.to_event_id:
            raise ValueError("An event cannot be linked to itself.")
        return self