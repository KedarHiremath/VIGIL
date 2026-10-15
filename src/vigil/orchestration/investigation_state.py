"""Runtime state of a VIGIL investigation workflow."""

from datetime import UTC, datetime
from enum import Enum

from pydantic import Field, model_validator

from vigil.domain.base import DomainModel
from vigil.domain.common import Identifier, ReferenceIds, Timestamp


class InvestigationStatus(str, Enum):
    """Lifecycle status of an investigation workflow."""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class InvestigationState(DomainModel):
    """Tracks progress and outputs of an investigation workflow."""

    investigation_id: Identifier = Field(
        description="Stable identifier for the investigation.",
    )

    status: InvestigationStatus = Field(
        default=InvestigationStatus.CREATED,
        description="Current lifecycle status of the investigation.",
    )

    task_ids: ReferenceIds = Field(
        default_factory=list,
        description="IDs of tasks associated with this investigation.",
    )

    observation_ids: ReferenceIds = Field(
        default_factory=list,
        description="IDs of observations produced during the investigation.",
    )

    event_ids: ReferenceIds = Field(
        default_factory=list,
        description="IDs of events identified during the investigation.",
    )

    started_at: Timestamp | None = Field(
        default=None,
        description="Optional timezone-aware time when the investigation began.",
    )

    updated_at: Timestamp = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timezone-aware time when the state was last updated.",
    )

    completed_at: Timestamp | None = Field(
        default=None,
        description=(
            "Timezone-aware time when the investigation reached a terminal state."
        ),
    )

    @model_validator(mode="after")
    def validate_state(self) -> "InvestigationState":
        """Ensure investigation status and timestamps are consistent."""
        if (
            self.status
            in {
                InvestigationStatus.COMPLETED,
                InvestigationStatus.FAILED,
            }
            and self.completed_at is None
        ):
            raise ValueError("Completed or failed investigations require completed_at.")

        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError("Completion time cannot precede investigation start time.")

        return self
