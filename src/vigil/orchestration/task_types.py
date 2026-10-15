"""Shared task and model-output contracts for VIGIL."""

import math
from datetime import UTC, datetime
from enum import Enum

from pydantic import Field, JsonValue, field_validator, model_validator

from vigil.domain.base import DomainModel


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

    task_id: str = Field(
        min_length=1,
        description="Stable unique identifier for this task.",
    )

    task_type: str = Field(
        min_length=1,
        description=(
            "Operation to perform, such as frame_sampling or visual_analysis."
        ),
    )

    input_refs: list[str] = Field(
        default_factory=list,
        description=(
            "IDs of the media assets, artifacts or other inputs required for the task."
        ),
    )

    parameters: dict[str, JsonValue] = Field(
        default_factory=dict,
        description="JSON-compatible parameters controlling the operation.",
    )

    requested_by: str | None = Field(
        default=None,
        description="Optional identifier of the agent or component requesting work.",
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timezone-aware time when the task request was created.",
    )

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        """Require a timezone-aware creation timestamp."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Task creation time must be timezone-aware.")
        return value

    @field_validator("task_id", "task_type", "requested_by")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        """Reject blank identifiers and task types."""
        if value is not None and not value.strip():
            raise ValueError("Identifiers and task types must not be blank.")
        return value

    @field_validator("input_refs")
    @classmethod
    def validate_input_refs(cls, values: list[str]) -> list[str]:
        """Reject blank or duplicate input references."""
        if any(not value.strip() for value in values):
            raise ValueError("Input references must not be blank.")
        if len(values) != len(set(values)):
            raise ValueError("Input references must not contain duplicates.")
        return values


class TaskResult(DomainModel):
    """Records the execution outcome of a task."""

    task_id: str = Field(
        min_length=1,
        description="ID of the task whose execution produced this result.",
    )

    status: TaskStatus = Field(
        description="Current execution outcome or lifecycle status.",
    )

    output_refs: list[str] = Field(
        default_factory=list,
        description=(
            "IDs of outputs produced by the task, such as observations or artifacts."
        ),
    )

    error: ErrorDetail | None = Field(
        default=None,
        description="Structured failure or partial-execution details, if any.",
    )

    started_at: datetime | None = Field(
        default=None,
        description="Optional timezone-aware time when execution began.",
    )

    completed_at: datetime | None = Field(
        default=None,
        description="Optional timezone-aware time when execution ended.",
    )

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, value: str) -> str:
        """Reject blank task IDs."""
        if not value.strip():
            raise ValueError("Task ID must not be blank.")
        return value

    @field_validator("output_refs")
    @classmethod
    def validate_output_refs(cls, values: list[str]) -> list[str]:
        """Reject blank or duplicate output references."""
        if any(not value.strip() for value in values):
            raise ValueError("Output references must not be blank.")
        if len(values) != len(set(values)):
            raise ValueError("Output references must not contain duplicates.")
        return values

    @field_validator("started_at", "completed_at")
    @classmethod
    def validate_timestamps(cls, value: datetime | None) -> datetime | None:
        """Require timezone-aware execution timestamps."""
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Execution timestamps must be timezone-aware.")
        return value

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

    output_id: str = Field(
        min_length=1,
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

    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description=("Optional producer-reported confidence score between 0 and 1."),
    )

    artifact_ids: list[str] = Field(
        default_factory=list,
        description="IDs of artifacts associated with the output.",
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timezone-aware time when the output was created.",
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float | None) -> float | None:
        """Reject non-finite confidence values."""
        if value is not None and not math.isfinite(value):
            raise ValueError("Confidence must be finite.")
        return value

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        """Require a timezone-aware output timestamp."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Output timestamp must be timezone-aware.")
        return value

    @field_validator("artifact_ids")
    @classmethod
    def validate_artifact_ids(cls, values: list[str]) -> list[str]:
        """Reject blank or duplicate artifact IDs."""
        if any(not value.strip() for value in values):
            raise ValueError("Artifact IDs must not be blank.")
        if len(values) != len(set(values)):
            raise ValueError("Artifact IDs must not contain duplicates.")
        return values
