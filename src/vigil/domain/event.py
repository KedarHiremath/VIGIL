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

    @model_validator(mode="after")
    def validate_time_order(self) -> "Event":
        """Reject an end time earlier than the start time."""
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time < self.start_time
        ):
            raise ValueError("Event end time cannot precede start time.")
        return self