"""VIGIL storage and repository contracts."""

from vigil.storage.repository import (
    EntityNotFoundError,
    InvestigationRepository,
    ReferentialIntegrityError,
)
from vigil.storage.sqlite_repository import SqliteInvestigationRepository

__all__ = [
    "EntityNotFoundError",
    "InvestigationRepository",
    "ReferentialIntegrityError",
    "SqliteInvestigationRepository",
]
