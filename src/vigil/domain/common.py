"""Reusable types and validation rules for VIGIL domain schemas."""

from typing import Annotated

from pydantic import (
    AfterValidator,
    AwareDatetime,
    Field,
    StringConstraints,
)


Identifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
    ),
]
"""A nonblank string identifier for a VIGIL object."""


Timestamp = AwareDatetime
"""A datetime that must include timezone information."""


ConfidenceScore = Annotated[
    float,
    Field(
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
    ),
]
"""An optional-to-use, normalized confidence score between 0 and 1."""


def validate_unique_reference_ids(values: list[str]) -> list[str]:
    """Reject blank or duplicate identifiers in a reference list."""
    normalized = [value.strip() for value in values]

    if any(not value for value in normalized):
        raise ValueError("Reference IDs must not be blank")

    if len(normalized) != len(set(normalized)):
        raise ValueError("Reference IDs must be unique")

    return normalized


ReferenceIds = Annotated[
    list[Identifier],
    AfterValidator(validate_unique_reference_ids),
]
"""A list of nonblank, unique object reference IDs."""