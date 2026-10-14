"""Shared validation rules for VIGIL domain schemas."""

from pydantic import BaseModel, ConfigDict


class DomainModel(BaseModel):
    """Base model for validated VIGIL domain objects."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        frozen=True,
    )
