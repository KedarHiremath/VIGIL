"""Provenance schema for traceable analysis results."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from vigil.domain.base import DomainModel
from vigil.domain.common import ReferenceIds, Timestamp


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
        min_length=1,
        description="Name of the model, tool, rule, agent, or person.",
    )

    producer_version: str | None = Field(
        default=None,
        description="Optional version of the producing component.",
    )

    method: str = Field(
        min_length=1,
        description="Analysis method or operation used to produce the result.",
    )

    input_artifact_ids: ReferenceIds = Field(
        default_factory=list,
        description="IDs of derived media artifacts consumed during analysis.",
    )

    parent_observation_ids: ReferenceIds = Field(
        default_factory=list,
        description=(
            "IDs of earlier observations used to derive or refine this result."
        ),
    )

    created_at: Timestamp = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timezone-aware timestamp when the result was produced.",
    )