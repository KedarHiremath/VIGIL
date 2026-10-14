"""Observation schema for media-analysis findings."""

import math
from typing import Literal

from pydantic import Field, field_validator

from vigil.domain.base import DomainModel
from vigil.domain.provenance import Provenance
from vigil.domain.source_reference import SourceReference


class Observation(DomainModel):
    """Represents a finding produced by analyzing source media."""

    observation_id: str = Field(
        min_length=1, description="Stable unique identifier for this observation."
    )

    modality: Literal["video", "audio", "image"] = Field(
        description="Media modality from which the finding was derived."
    )

    observation_type: str = Field(
        min_length=1,
        description=(
            "Kind of finding, such as person_detection, motion, "
            "action, or audio_transcription."
        ),
    )

    description: str = Field(
        min_length=1, description="Human-readable description of the finding."
    )

    source_references: list[SourceReference] = Field(
        min_length=1,
        description=("One or more source-media intervals supporting the observation."),
    )

    artifact_ids: list[str] = Field(
        default_factory=list,
        description="IDs of derived artifacts associated with the finding.",
    )

    confidence: float | None = Field(
        default=None,
        ge=0,
        le=1,
        description=(
            "Optional producer-reported confidence score between 0 and 1; "
            "not necessarily a calibrated probability."
        ),
    )

    provenance: Provenance = Field(
        description="Record of how this observation was produced."
    )

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: float | None) -> float | None:
        """Reject NaN and infinite confidence scores."""
        if value is not None and not math.isfinite(value):
            raise ValueError("Confidence must be finite.")
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
