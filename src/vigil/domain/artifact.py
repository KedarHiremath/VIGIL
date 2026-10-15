"""Derived media artifact schema."""

import re
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from vigil.domain.base import DomainModel
from vigil.domain.common import Identifier, Timestamp
from vigil.domain.source_reference import SourceReference


class Artifact(DomainModel):
    """Represents media derived from an original source."""

    artifact_id: Identifier = Field(
        description="Stable unique identifier for the derived artifact.",
    )

    artifact_type: Literal[
        "frame",
        "crop",
        "clip",
        "audio_segment",
        "derived_media",
    ] = Field(
        description="Operation-specific kind of derived media.",
    )

    media_type: Literal["video", "audio", "image"] = Field(
        description="Actual media type stored by this artifact.",
    )

    storage_uri: str = Field(
        min_length=1,
        description="Storage location of the derived media.",
    )

    source_reference: SourceReference = Field(
        description=(
            "Original media and timeline interval from which this artifact was derived."
        ),
    )

    sha256: str | None = Field(
        default=None,
        description=(
            "Optional SHA-256 checksum of the derived artifact, "
            "represented by exactly 64 hexadecimal characters."
        ),
    )

    created_at: Timestamp = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timezone-aware timestamp when the artifact was created.",
    )

    @field_validator("storage_uri")
    @classmethod
    def validate_storage_uri(cls, value: str) -> str:
        """Reject blank artifact locations."""
        if not value.strip():
            raise ValueError("Storage URI must not be blank.")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str | None) -> str | None:
        """Validate the optional SHA-256 checksum."""
        if value is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            raise ValueError("SHA-256 must contain 64 hexadecimal characters.")
        return value

    @model_validator(mode="after")
    def validate_artifact_type(self) -> "Artifact":
        """Ensure the artifact kind matches its media type."""
        expected_types = {
            "frame": "image",
            "crop": "image",
            "clip": "video",
            "audio_segment": "audio",
        }

        expected = expected_types.get(self.artifact_type)
        if expected is not None and self.media_type != expected:
            raise ValueError(
                f"Artifact type '{self.artifact_type}' "
                f"requires media type '{expected}'."
            )

        return self