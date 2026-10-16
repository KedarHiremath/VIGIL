"""Evidence quality and support assessment schema."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from vigil.domain.base import DomainModel
from vigil.domain.common import Identifier, Timestamp


class EvidenceAssessment(DomainModel):
    """Records an assessment of evidence supporting an observation or event."""

    assessment_id: Identifier = Field(
        description="Stable unique identifier for this assessment.",
    )

    target_type: Literal["observation", "event"] = Field(
        description="Type of record being assessed.",
    )

    target_id: Identifier = Field(
        description="ID of the observation or event being assessed.",
    )

    assessment_type: Literal[
        "evidence_quality",
        "support_level",
        "uncertainty",
    ] = Field(description="Dimension of evidence being evaluated.")

    rating: Literal[
        "insufficient",
        "low",
        "moderate",
        "high",
    ] = Field(description="Qualitative assessment of the selected dimension.")

    rationale: str = Field(
        min_length=1,
        description="Explanation supporting the assessment.",
    )

    assessed_by: str = Field(
        min_length=1,
        description="Name or identifier of the assessor or assessment tool.",
    )

    created_at: Timestamp = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timezone-aware time when the assessment was recorded.",
    )
