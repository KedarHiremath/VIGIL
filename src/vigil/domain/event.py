"""Event schema for investigation occurrences."""

from typing import Literal

from pydantic import Field, model_validator

from vigil.domain.base import DomainModel
from vigil.domain.common import Identifier, ReferenceIds, Timestamp


class Event(DomainModel):
    """Represents an occurrence supported by investigation evidence."""

    event_id: Identifier = Field(
        description="Stable unique identifier for this event.",
    )

    event_type: str = Field(
        min_length=1,
        description=(
            "Category of occurrence, such as restricted_area_entry "
            "or vehicle_departure."
        ),
    )

    description: str = Field(
        min_length=1,
        description="Human-readable description of the occurrence.",
    )

    observation_ids: ReferenceIds = Field(
        min_length=1,
        description="Observation IDs supporting this event.",
    )

    entity_ids: ReferenceIds = Field(
        default_factory=list,
        description="Optional entity IDs associated with the event.",
    )

    status: Literal[
        "proposed",
        "under_review",
        "confirmed",
        "rejected",
    ] = Field(default="proposed", description="Current review state of the event.")

    start_time: Timestamp | None = Field(
        default=None,
        description="Optional timezone-aware estimated wall-clock start time.",
    )

    end_time: Timestamp | None = Field(
        default=None,
        description="Optional timezone-aware estimated wall-clock end time.",
    )

    start_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Optional footage-relative start offset in seconds.",
    )

    end_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Optional footage-relative end offset in seconds.",
    )

    reviewer: str | None = Field(
        default=None,
        description="Investigator identifier who reviewed or edited this event.",
    )

    review_notes: str | None = Field(
        default=None,
        description="Investigator notes or rationale recorded during review.",
    )

    reviewed_at: Timestamp | None = Field(
        default=None,
        description="Timezone-aware timestamp when review occurred.",
    )

    @model_validator(mode="after")
    def validate_time_order(self) -> "Event":
        """Reject an end time earlier than the start time."""
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time < self.start_time
        ):
            raise ValueError("Event end time cannot precede start time.")
        if (
            self.start_seconds is not None
            and self.end_seconds is not None
            and self.end_seconds < self.start_seconds
        ):
            raise ValueError("Event end seconds cannot precede start seconds.")
        return self
