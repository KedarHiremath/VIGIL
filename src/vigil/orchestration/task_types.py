
"""Shared task and model-output contracts for VIGIL."""

import math
from datetime import UTC, datetime
from enum import Enum

from pydantic import Field, JsonValue, field_validator, model_validator

from vigil.domain.base import DomainModel
from vigil.domain.common import (
    ConfidenceScore,
    Identifier,
    ReferenceIds,
    Timestamp,
)


class TaskStatus(str, Enum):
    """Lifecycle status of an execution task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class ErrorDetail(DomainModel):
    """Structured information describing an execution error."""

    code: str = Field(
        min_length=1,
        description="Stable machine-readable error code.",
    )

    message: str = Field(
        min_length=1,
        description="Human-readable explanation of the error.",
    )

    retryable: bool = Field(
        description="Whether retrying the operation may succeed.",
    )

    retry_after_seconds: float | None = Field(
        default=None,
        ge=0,
        description="Optional minimum delay before retrying, in seconds.",
    )

    @field_validator("retry_after_seconds")
    @classmethod
    def validate_retry_delay(cls, value: float | None) -> float | None:
        """Reject non-finite retry delays."""
        if value is not None and not math.isfinite(value):
            raise ValueError("Retry delay must be finite.")
        return value

    @field_validator("code", "message")
    @classmethod
    def validate_nonblank_text(cls, value: str) -> str:
        """Reject blank error codes and messages."""
        if not value.strip():
            raise ValueError("Error text must not be blank.")
        return value

    @model_validator(mode="after")
    def validate_retry_policy(self) -> "ErrorDetail":
        """Allow retry delays only for retryable errors."""
        if self.retry_after_seconds is not None and not self.retryable:
            raise ValueError("A retry delay requires a retryable error.")
        return self


class TaskRequest(DomainModel):
    """Defines a request for a tool or agent to perform work."""

    task_id: Identifier = Field(
        description="Stable unique identifier for this task.",
    )

    task_type: str = Field(
        min_length=1,
        description=(
            "Operation to perform, such as frame_sampling or visual_analysis."
        ),
    )

    input_refs: ReferenceIds = Field(
        default_factory=list,
        description=(
            "IDs of the media assets, artifacts or other inputs required for the task."
        ),
    )

    parameters: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="JSON-compatible parameters controlling the operation.",
    )

    requested_by: Identifier | None = Field(
        default=None,
        description="Optional identifier of the agent or component requesting work.",
    )

    created_at: Timestamp = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timezone-aware time when the task request was created.",
    )

    @field_validator("task_type")
    @classmethod
    def validate_task_type(cls, value: str) -> str:
        """Reject blank task types."""
        if not value.strip():
            raise ValueError("Task type must not be blank.")
        return value


class TaskResult(DomainModel):
    """Records the execution outcome of a task."""

    task_id: Identifier = Field(
        description="ID of the task whose execution produced this result.",
    )

    status: TaskStatus = Field(
        description="Current execution outcome or lifecycle status.",
    )

    output_refs: ReferenceIds = Field(
        default_factory=list,
        description=(
            "IDs of outputs produced by the task, such as observations or artifacts."
        ),
    )

    error: ErrorDetail | None = Field(
        default=None,
        description="Structured failure or partial-execution details, if any.",
    )

    started_at: Timestamp | None = Field(
        default=None,
        description="Optional timezone-aware time when execution began.",
    )

    completed_at: Timestamp | None = Field(
        default=None,
        description="Optional timezone-aware time when execution ended.",
    )

    @model_validator(mode="after")
    def validate_result(self) -> "TaskResult":
        """Keep task status, errors and timestamps consistent."""
        if self.status == TaskStatus.FAILED and self.error is None:
            raise ValueError("A failed task must include error details.")

        if self.status == TaskStatus.COMPLETED and self.error is not None:
            raise ValueError("A completed task must not include an error.")

        if (
            self.started_at is not None
            and self.completed_at is not None
            and self.completed_at < self.started_at
        ):
            raise ValueError("Completion time cannot precede start time.")

        return self


class ModelOutput(DomainModel):
    """Represents structured output from a model or analysis tool."""

    output_id: Identifier = Field(
        description="Stable unique identifier for this output.",
    )

    producer_name: str = Field(
        min_length=1,
        description="Name of the model or analysis tool producing the output.",
    )

    output_type: str = Field(
        min_length=1,
        description=(
            "Kind of output, such as frame_description, detection or transcription."
        ),
    )

    payload: dict[str, JsonValue] = Field(
        description="JSON-compatible structured output produced by the tool.",
    )

    confidence: ConfidenceScore | None = Field(
        default=None,
        description=(
            "Optional producer-reported confidence score between 0 and 1."
        ),
    )

    artifact_ids: ReferenceIds = Field(
        default_factory=list,
        description="IDs of artifacts associated with the output.",
    )

    created_at: Timestamp = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timezone-aware time when the output was created.",
    )
