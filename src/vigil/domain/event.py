"""Event schema for investigation occurrences."""

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from vigil.domain.base import DomainModel


class Event(DomainModel):
    """Represents an occurrence supported by investigation evidence."""

    event_id: str = Field(
        min_length=1, description="Stable unique identifier for this event."
    )

    event_type: str = Field(
        min_length=1,
        description=(
            "Category of occurrence, such as restricted_area_entry "
            "or vehicle_departure."
        ),
    )

    description: str = Field(
        min_length=1, description="Human-readable description of the occurrence."
    )

    observation_ids: list[str] = Field(
        min_length=1, description="Observation IDs supporting this event."
    )

    entity_ids: list[str] = Field(
        default_factory=list,
        description="Optional entity IDs associated with the event.",
    )

    status: Literal[
        "proposed",
        "under_review",
        "confirmed",
        "rejected",
    ] = Field(default="proposed", description="Current review state of the event.")

    start_time: datetime | None = Field(
        default=None,
        description=("Optional timezone-aware estimated wall-clock start time."),
    )

    end_time: datetime | None = Field(
        default=None,
        description=("Optional timezone-aware estimated wall-clock end time."),
    )

    @field_validator("observation_ids", "entity_ids")
    @classmethod
    def validate_references(cls, values: list[str]) -> list[str]:
        """Reject blank or duplicate references."""
        if any(not value.strip() for value in values):
            raise ValueError("References must not be blank.")
        if len(values) != len(set(values)):
            raise ValueError("References must not contain duplicates.")
        return values

    @field_validator("start_time", "end_time")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        """Require timezone-aware event timestamps."""
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Event timestamps must be timezone-aware.")
        return value

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
