"""Observation schema for media-analysis findings."""

from typing import Literal

from pydantic import Field

from vigil.domain.base import DomainModel
from vigil.domain.common import ConfidenceScore, Identifier, ReferenceIds
from vigil.domain.provenance import Provenance
from vigil.domain.source_reference import SourceReference


class Observation(DomainModel):
    """Represents a finding produced by analyzing source media."""

    observation_id: Identifier = Field(
        description="Stable unique identifier for this observation.",
    )

    modality: Literal["video", "audio", "image"] = Field(
        description="Media modality from which the finding was derived.",
    )

    observation_type: str = Field(
        min_length=1,
        description=(
            "Kind of finding, such as person_detection, motion, "
            "action, or audio_transcription."
        ),
    )

    description: str = Field(
        min_length=1,
        description="Human-readable description of the finding.",
    )

    source_references: list[SourceReference] = Field(
        min_length=1,
        description="One or more source-media intervals supporting the observation.",
    )

    artifact_ids: ReferenceIds = Field(
        default_factory=list,
        description="IDs of derived artifacts associated with the finding.",
    )

    confidence: ConfidenceScore | None = Field(
        default=None,
        description=(
            "Optional producer-reported confidence score between 0 and 1; "
            "not necessarily a calibrated probability."
        ),
    )

    provenance: Provenance = Field(
        description="Record of how this observation was produced.",
    )