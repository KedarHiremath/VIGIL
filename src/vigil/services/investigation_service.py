"""Application service coordinating media ingestion, agentic orchestration, and telemetry."""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from vigil.agent.investigator import AgenticOrchestrator, InvestigationOutcome
from vigil.config import config
from vigil.domain.artifact import Artifact
from vigil.domain.coverage import CoverageRecord
from vigil.domain.event import Event
from vigil.domain.investigation import Investigation
from vigil.domain.observation import Observation
from vigil.domain.report import Report
from vigil.media.ingestion import IngestionResult, MediaIngestionService
from vigil.orchestration.investigation_state import (
    InvestigationState,
    InvestigationStatus,
)
from vigil.services.telemetry import TelemetryManager
from vigil.storage.repository import InvestigationRepository
from vigil.storage.sqlite_repository import SqliteInvestigationRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InvestigationStatusInfo:
    """Detailed runtime status and metric summary for an active or completed investigation."""

    investigation_id: str
    status: InvestigationStatus
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    completed_tasks: int
    task_ids: list[str]
    observation_count: int
    event_count: int
    coverage_count: int
    has_report: bool
    report_id: str | None = None
    error: str | None = None


class InvestigationService:
    """Core application service managing investigations across media ingestion and agentic workflows."""

    def __init__(
        self,
        repository: InvestigationRepository | None = None,
        orchestrator: AgenticOrchestrator | None = None,
        telemetry: TelemetryManager | None = None,
        media_service: MediaIngestionService | None = None,
        storage_dir: Path | str | None = None,
        max_workers: int = 4,
    ) -> None:
        if repository is None:
            # File-backed SQLite database from config or fallback
            db_path = Path(config.storage_root) / "vigil.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            self.repository: InvestigationRepository = SqliteInvestigationRepository(
                db_path=db_path
            )
        else:
            self.repository = repository

        self.telemetry = telemetry or TelemetryManager()
        self.media_service = media_service or MediaIngestionService(self.repository)
        self.orchestrator = orchestrator or AgenticOrchestrator(
            repository=self.repository
        )

        self.storage_dir = (
            Path(storage_dir).resolve()
            if storage_dir
            else Path(config.storage_root).resolve()
        )
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="vigil-investigation-worker",
        )
        self._lock = threading.RLock()
        self._active_jobs: dict[str, Future[InvestigationOutcome]] = {}

    def shutdown(self, wait: bool = True) -> None:
        """Shutdown background worker pool."""
        self._executor.shutdown(wait=wait)

    def create_and_ingest_investigation(
        self,
        file_path: Path | str,
        investigation_id: str | None = None,
        title: str | None = None,
        objective: str | None = None,
        scope_description: str | None = None,
        camera_id: str | None = None,
        camera_name: str | None = None,
        camera_location: str | None = None,
        camera_timezone: str | None = None,
        sample_interval_seconds: float = 2.0,
        max_frames: int = 50,
        extract_audio: bool = True,
        created_by: str | None = None,
    ) -> tuple[Investigation, IngestionResult]:
        """Ingest physical media file, register assets in repository, and create Investigation domain model."""
        inv_id = investigation_id or f"inv-{uuid.uuid4().hex[:8]}"
        path = Path(file_path).resolve()

        if not path.is_file():
            raise FileNotFoundError(f"Source media file not found: {path}")

        # Ingest media file into repository
        artifacts_dir = self.storage_dir / "artifacts" / inv_id
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        ingestion_result = self.media_service.ingest_file(
            file_path=path,
            camera_id=camera_id,
            camera_name=camera_name,
            camera_location=camera_location,
            camera_timezone=camera_timezone,
            sample_interval_seconds=sample_interval_seconds,
            max_frames=max_frames,
            extract_audio=extract_audio,
            output_artifacts_dir=artifacts_dir,
        )

        # Build investigation domain model
        inv_title = title or f"Investigation: {path.name}"
        inv_objective = (
            objective or "Perform comprehensive forensic video and audio examination."
        )
        inv_scope = (
            scope_description
            or f"Physical media footage analysis from {path.name}"
        )

        investigation = Investigation(
            investigation_id=inv_id,
            title=inv_title,
            objective=inv_objective,
            scope_description=inv_scope,
            media_asset_ids=[ingestion_result.media_asset.media_asset_id],
            created_by=created_by or "vigil-api-user",
        )
        self.repository.add_investigation(investigation)

        # Initialize state
        initial_state = InvestigationState(
            investigation_id=inv_id,
            status=InvestigationStatus.CREATED,
        )
        self.repository.save_state(initial_state)

        # Broadcast creation event
        self.telemetry.broadcast(
            investigation_id=inv_id,
            event_type="investigation_created",
            data={
                "investigation_id": inv_id,
                "title": inv_title,
                "media_asset_id": ingestion_result.media_asset.media_asset_id,
                "frame_count": len(ingestion_result.frame_artifacts),
                "has_audio": len(ingestion_result.audio_artifacts) > 0,
            },
        )

        return investigation, ingestion_result

    def run_investigation(
        self,
        investigation_id: str,
        run_async: bool = True,
    ) -> InvestigationOutcome | None:
        """Trigger agentic investigation pipeline synchronously or asynchronously."""
        inv = self.repository.get_investigation(investigation_id)
        callback = self.telemetry.create_callback(investigation_id)

        if not run_async:
            return self.orchestrator.run_investigation(
                inv, event_callback=callback
            )

        def _worker() -> InvestigationOutcome:
            try:
                return self.orchestrator.run_investigation(
                    inv, event_callback=callback
                )
            except Exception as exc:
                logger.exception(f"Investigation {investigation_id} failed")
                self.telemetry.broadcast(
                    investigation_id=investigation_id,
                    event_type="investigation_error",
                    data={"investigation_id": investigation_id, "error": str(exc)},
                )
                raise

        with self._lock:
            future = self._executor.submit(_worker)
            self._active_jobs[investigation_id] = future

        return None

    def get_status(self, investigation_id: str) -> InvestigationStatusInfo:
        """Query lifecycle state and progress metrics for an investigation."""
        inv = self.repository.get_investigation(investigation_id)
        state = self.repository.get_state(investigation_id)

        if state is None:
            state = InvestigationState(
                investigation_id=investigation_id,
                status=InvestigationStatus.CREATED,
            )

        # Find if report exists
        reports = self.repository.list_reports(investigation_id)
        has_report = len(reports) > 0
        latest_report_id = reports[-1].report_id if has_report else None

        # Check for error if job failed in future
        error_msg: str | None = None
        with self._lock:
            future = self._active_jobs.get(investigation_id)
            if future and future.done() and future.exception():
                error_msg = str(future.exception())

        # Coverage count
        coverages = self.repository.list_coverage_records(investigation_id)

        return InvestigationStatusInfo(
            investigation_id=inv.investigation_id,
            status=state.status,
            created_at=inv.created_at,
            updated_at=state.updated_at,
            started_at=state.started_at,
            completed_at=state.completed_at,
            completed_tasks=len(state.task_ids),
            task_ids=list(state.task_ids),
            observation_count=len(state.observation_ids),
            event_count=len(state.event_ids),
            coverage_count=len(coverages),
            has_report=has_report,
            report_id=latest_report_id,
            error=error_msg,
        )

    def get_report(self, investigation_id: str) -> Report | None:
        """Retrieve compiled forensic report for an investigation."""
        # Ensure investigation exists
        self.repository.get_investigation(investigation_id)
        reports = self.repository.list_reports(investigation_id)
        if not reports:
            return None
        return reports[-1]

    def list_investigations(self) -> list[Investigation]:
        """List all known investigations."""
        return self.repository.list_investigations()

    def get_investigation(self, investigation_id: str) -> Investigation:
        """Fetch investigation domain object."""
        return self.repository.get_investigation(investigation_id)

    def get_observations(self, investigation_id: str) -> list[Observation]:
        """Fetch all observations recorded for an investigation."""
        state = self.repository.get_state(investigation_id)
        if state is None:
            return []
        return self.repository.list_observations(state.observation_ids)

    def get_events(self, investigation_id: str) -> list[Event]:
        """Fetch all events recorded for an investigation."""
        state = self.repository.get_state(investigation_id)
        if state is None:
            return []
        return self.repository.list_events(state.event_ids)

    def get_coverage_records(self, investigation_id: str) -> list[CoverageRecord]:
        """Fetch all coverage records for an investigation."""
        return self.repository.list_coverage_records(investigation_id)

    def get_artifacts(self, investigation_id: str) -> list[Artifact]:
        """Fetch all artifacts associated with the investigation's media assets."""
        inv = self.repository.get_investigation(investigation_id)
        all_artifacts = self.repository.list_artifacts()
        inv_asset_ids = set(inv.media_asset_ids)
        return [
            a
            for a in all_artifacts
            if a.source_reference.media_asset_id in inv_asset_ids
        ]
