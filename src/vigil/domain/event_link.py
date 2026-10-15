"""Relationship schema between investigation events."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, model_validator

from vigil.domain.base import DomainModel
from vigil.domain.common import ConfidenceScore, Identifier, Timestamp


class EventLink(DomainModel):
    """Represents a typed relationship between two distinct events."""

    event_link_id: Identifier = Field(
        description="Stable unique identifier for this relationship.",
    )

    from_event_id: Identifier = Field(
        description="ID of the source event in the relationship.",
    )

    to_event_id: Identifier = Field(
        description="ID of the destination event in the relationship.",
    )

    relationship_type: Literal[
        "before",
        "after",
        "overlaps",
        "related_to",
        "possible_same_incident",
    ] = Field(description="Type of relationship between the two events.")

    rationale: str = Field(
        min_length=1,
        description="Explanation for recording this relationship.",
    )

    confidence: ConfidenceScore | None = Field(
        default=None,
        description=(
            "Optional producer-reported confidence score; "
            "not necessarily a calibrated probability."
        ),
    )

    created_at: Timestamp = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timezone-aware time when the relationship was recorded.",
    )

    @model_validator(mode="after")
    def validate_distinct_events(self) -> "EventLink":
        """Prevent an event from being linked to itself."""
        if self.from_event_id == self.to_event_id:
            raise ValueError("An event cannot be linked to itself.")
        return self
