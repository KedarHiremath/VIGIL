"""VIGIL storage and repository contracts."""

from vigil.storage.repository import (
    EntityNotFoundError,
    InvestigationRepository,
    ReferentialIntegrityError,
)

__all__ = [
    "EntityNotFoundError",
    "InvestigationRepository",
    "ReferentialIntegrityError",
]
