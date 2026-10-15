
"""Domain schema for an investigation."""

from datetime import UTC, datetime

from pydantic import Field, field_validator

from vigil.domain.base import DomainModel
from vigil.domain.common import Identifier, ReferenceIds, Timestamp


class Investigation(DomainModel):
    """Defines an investigation and the media within its scope."""

    investigation_id: Identifier = Field(
        description="Stable identifier for this investigation.",
    )
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    scope_description: str = Field(min_length=1)

    media_asset_ids: ReferenceIds = Field(default_factory=list)
    source_reference_ids: ReferenceIds = Field(default_factory=list)

    created_at: Timestamp = Field(default_factory=lambda: datetime.now(UTC))
    created_by: Identifier | None = None

    @field_validator("title", "objective", "scope_description")
    @classmethod
    def reject_blank_text(cls, value: str) -> str:
        """Reject blank required text."""
        if not value.strip():
            raise ValueError("Value must not be blank")
        return value
