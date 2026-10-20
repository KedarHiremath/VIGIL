"""FastAPI dependency providers for VIGIL services and storage."""

from __future__ import annotations

import functools
from pathlib import Path

from vigil.config import config
from vigil.services.investigation_service import InvestigationService
from vigil.services.telemetry import TelemetryManager
from vigil.storage.sqlite_repository import SqliteInvestigationRepository


@functools.lru_cache(maxsize=1)
def get_telemetry_manager() -> TelemetryManager:
    """Provide singleton TelemetryManager instance."""
    return TelemetryManager()


@functools.lru_cache(maxsize=1)
def get_investigation_service() -> InvestigationService:
    """Provide application InvestigationService backed by persistent SQLite."""
    storage_root = Path(config.storage_root).resolve()
    storage_root.mkdir(parents=True, exist_ok=True)
    db_path = storage_root / "vigil.db"

    repo = SqliteInvestigationRepository(db_path=db_path)
    telemetry = get_telemetry_manager()

    return InvestigationService(
        repository=repo,
        telemetry=telemetry,
        storage_dir=storage_root,
    )
