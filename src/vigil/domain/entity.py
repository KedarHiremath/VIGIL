"""Entity schema for detected or tracked objects."""

import math
from typing import Literal

from pydantic import Field, field_validator

from vigil.domain.base import DomainModel
from vigil.domain.common import Identifier, ReferenceIds


class Entity(DomainModel):
    """Represents a detected or tracked entity in an investigation."""

    entity_id: Identifier = Field(
        description="Stable identifier for this tracked entity.",
    )

    entity_type: Literal[
        "person",
        "vehicle",
        "animal",
        "object",
        "unknown",
    ] = Field(description="Category assigned to the detected or tracked entity.")

    label: str | None = Field(
        default=None,
        description=(
            "Optional human-readable label; not necessarily a verified identity."
        ),
    )

    associated_observation_ids: ReferenceIds = Field(
        min_length=1,
        description="IDs of observations associated with this entity.",
    )

    attributes: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict,
        description="Optional structured attributes, such as color or vehicle type.",
    )

    @field_validator("attributes")
    @classmethod
    def validate_attributes(
        cls,
        values: dict[str, str | int | float | bool | None],
    ) -> dict[str, str | int | float | bool | None]:
        """Reject blank attribute names and non-finite numeric values."""
        for key, value in values.items():
            if not key.strip():
                raise ValueError("Attribute names must not be blank.")
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError("Numeric attributes must be finite.")
        return values
