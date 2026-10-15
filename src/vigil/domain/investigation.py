"""Domain schema for an investigation."""
from datetime import UTC, datetime

from pydantic import Field, field_validator

from vigil.domain.base import DomainModel


class Investigation(DomainModel):
    """Defines an investigation and the media within its scope."""

    investigation_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    scope_description: str = Field(min_length=1)

    media_asset_ids: list[str] = Field(default_factory=list)
    source_reference_ids: list[str] = Field(default_factory=list)

    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )
    created_by: str | None = None

    @field_validator(
        "investigation_id",
        "title",
        "objective",
        "scope_description",
        "created_by",
    )
    @classmethod
    def reject_blank_text(cls, value: str | None) -> str | None:
        """Reject blank required text and blank optional creator IDs."""
        if value is not None and not value.strip():
            raise ValueError("Value must not be blank")
        return value

    @field_validator("media_asset_ids", "source_reference_ids")
    @classmethod
    def validate_unique_references(
        cls, values: list[str]
    ) -> list[str]:
        """Require nonblank and unique reference IDs."""
        if any(not value.strip() for value in values):
            raise ValueError("Reference IDs must not be blank")
        if len(values) != len(set(values)):
            raise ValueError("Reference IDs must be unique")
        return values

    @field_validator("created_at")
    @classmethod
    def require_timezone_aware_created_at(
        cls, value: datetime
    ) -> datetime:
        """Require a timezone-aware creation timestamp."""
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("created_at must be timezone-aware")
        return value