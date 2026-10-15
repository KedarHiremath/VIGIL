"""Runtime state of a VIGIL investigation workflow."""

from datetime import UTC, datetime
from enum import Enum

from pydantic import Field, field_validator, model_validator

from vigil.domain.base import DomainModel


class InvestigationStatus(str, Enum):
    """Lifecycle status of an investigation workflow."""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class InvestigationState(DomainModel):
    """Tracks progress and outputs of an investigation workflow."""

    investigation_id: str = Field(
        min_length=1,
        description="Stable identifier for the investigation.",
    )

    status: InvestigationStatus = Field(
        default=InvestigationStatus.CREATED,
        description="Current lifecycle status of the investigation.",
    )

    task_ids: list[str] = Field(
        default_factory=list,
        description="IDs of tasks associated with this investigation.",
    )

    observation_ids: list[str] = Field(
        default_factory=list,
        description="IDs of observations produced during the investigation.",
    )

    event_ids: list[str] = Field(
        default_factory=list,
        description="IDs of events identified during the investigation.",
    )

    started_at: datetime | None = Field(
        default=None,
        description="Optional timezone-aware time when the investigation began.",
    )

    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timezone-aware time when the state was last updated.",
    )

    completed_at: datetime | None = Field(
        default=None,
        description=(
            "Timezone-aware time when the investigation reached a terminal state."
        ),
    )

    @field_validator("investigation_id")
    @classmethod
    def validate_investigation_id(cls, value: str) -> str:
        """Reject blank investigation IDs."""
        if not value.strip():
            raise ValueError("Investigation ID must not be blank.")
        return value

    @field_validator("task_ids", "observation_ids", "event_ids")
    @classmethod
    def validate_references(cls, values: list[str]) -> list[str]:
        """Reject blank or duplicate references."""
        if any(not value.strip() for value in values):
            raise ValueError("References must not be blank.")
        if len(values) != len(set(values)):
            raise ValueError("References must not contain duplicates.")
        return values

    @field_validator("started_at", "updated_at", "completed_at")
    @classmethod
    def validate_timestamps(
        cls, value: datetime | None
    ) -> datetime | None:
        """Require timezone-aware timestamps."""
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("Investigation timestamps must be timezone-aware.")
        return value

    @model_validator(mode="after")
    def validate_state(self) -> "InvestigationState":
        """Ensure investigation status and timestamps are consistent."""
        if (
            self.status in {
                InvestigationStatus.COMPLETED,
                InvestigationStatus.FAILED,
            }
            and self.completed_at is None
        ):
            raise ValueError(
                "Completed or failed investigations require completed_at."
            )

        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError(
                "Completion time cannot precede investigation start time."
            )

        return self