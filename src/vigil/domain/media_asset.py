"""Original media asset schema."""

import math
import re
from typing import Literal

from pydantic import Field, field_validator

from vigil.domain.base import DomainModel
from vigil.domain.common import Identifier, Timestamp


class MediaAsset(DomainModel):
    """Represents an original video, audio, or image asset."""

    media_asset_id: Identifier = Field(
        description="Stable unique identifier for the original media.",
    )

    media_type: Literal["video", "audio", "image"] = Field(
        description="Type of original media.",
    )

    storage_uri: str = Field(
        min_length=1,
        description=(
            "Location or storage key for the original media, "
            "such as a file URI or object-storage URI."
        ),
    )

    camera_id: Identifier | None = Field(
        default=None,
        description="Optional ID of the camera that produced this media.",
    )

    duration_seconds: float | None = Field(
        default=None,
        gt=0,
        description=(
            "Optional media duration in seconds; omit when unknown "
            "or not applicable, such as for a still image."
        ),
    )

    recorded_at: Timestamp | None = Field(
        default=None,
        description=(
            "Optional timezone-aware wall-clock time corresponding "
            "to the beginning of the recording."
        ),
    )

    sha256: str | None = Field(
        default=None,
        description=(
            "Optional SHA-256 checksum of the original media, "
            "represented by exactly 64 hexadecimal characters."
        ),
    )

    @field_validator("storage_uri")
    @classmethod
    def validate_storage_uri(cls, value: str) -> str:
        """Reject blank storage references."""
        if not value.strip():
            raise ValueError("Storage URI must not be blank.")
        return value

    @field_validator("duration_seconds")
    @classmethod
    def validate_duration(cls, value: float | None) -> float | None:
        """Reject non-finite durations."""
        if value is not None and not math.isfinite(value):
            raise ValueError("Duration must be finite.")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str | None) -> str | None:
        """Validate the optional SHA-256 checksum."""
        if value is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", value):
            raise ValueError("SHA-256 must contain 64 hexadecimal characters.")
        return value