"""Provenance schema for traceable analysis results."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, field_validator

from vigil.domain.base import DomainModel


class Provenance(DomainModel):
    """Records how an observation or derived result was produced."""

    producer_type: Literal[
        "vision_model",
        "audio_model",
        "rule",
        "agent",
        "human",
        "other",
    ] = Field(description="Category of the component or person producing the result.")

    producer_name: str = Field(
        min_length=1, description="Name of the model, tool, rule, agent, or person."
    )

    producer_version: str | None = Field(
        default=None, description="Optional version of the producing component."
    )

    method: str = Field(
        min_length=1,
        description="Analysis method or operation used to produce the result.",
    )

    input_artifact_ids: list[str] = Field(
        default_factory=list,
        description="IDs of derived media artifacts consumed during analysis.",
    )

    parent_observation_ids: list[str] = Field(
        default_factory=list,
        description=(
            "IDs of earlier observations used to derive or refine this result."
        ),
    )

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timezone-aware timestamp when the result was produced.",
    )

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        """Require a timezone-aware creation timestamp."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Creation timestamp must be timezone-aware.")
        return value

    @field_validator("input_artifact_ids", "parent_observation_ids")
    @classmethod
    def validate_unique_references(cls, values: list[str]) -> list[str]:
        """Reject blank or duplicate references."""
        if any(not value.strip() for value in values):
            raise ValueError("References must not be blank.")
        if len(values) != len(set(values)):
            raise ValueError("References must not contain duplicates.")
        return values
