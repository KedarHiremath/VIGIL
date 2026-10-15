"""Camera metadata schema."""

import math
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator

from vigil.domain.base import DomainModel
from vigil.domain.common import Identifier


class Camera(DomainModel):
    """Represents a camera or recording source."""

    camera_id: Identifier = Field(
        description="Stable unique identifier for this camera.",
    )

    name: str = Field(
        min_length=1,
        description="Human-readable name assigned to the camera.",
    )

    location_label: str | None = Field(
        default=None,
        description="Optional physical location, such as Parking Entrance.",
    )

    timezone: str | None = Field(
        default=None,
        description="Optional IANA timezone, such as Asia/Kolkata.",
    )

    clock_offset_seconds: float | None = Field(
        default=None,
        description=(
            "Optional correction in seconds applied to the camera's "
            "reported clock to estimate reference time."
        ),
    )

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        """Reject unknown IANA timezone names."""
        if value is None:
            return None

        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Unknown IANA timezone.") from exc

        return value

    @field_validator("clock_offset_seconds")
    @classmethod
    def validate_clock_offset(cls, value: float | None) -> float | None:
        """Reject infinite and NaN clock offsets."""
        if value is not None and not math.isfinite(value):
            raise ValueError("Clock offset must be finite.")

        return value
