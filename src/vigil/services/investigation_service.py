"""Application service coordinating media ingestion, agentic orchestration, and telemetry."""

from __future__ import annotations

import logging
import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vigil.agent.investigator import AgenticOrchestrator, InvestigationOutcome
from vigil.config import config
from vigil.domain.artifact import Artifact
from vigil.domain.audit import AuditLog
from vigil.domain.coverage import CoverageRecord
from vigil.domain.event import Event
from vigil.domain.evidence_assessment import EvidenceAssessment
from vigil.domain.investigation import Investigation
from vigil.domain.media_asset import MediaAsset
from vigil.domain.observation import Observation
from vigil.domain.provenance import Provenance
from vigil.domain.report import Report
from vigil.domain.source_reference import SourceReference
from vigil.media.ingestion import IngestionResult, MediaIngestionService
from vigil.media.slicer import ClipSlicer
from vigil.orchestration.investigation_state import (
    InvestigationState,
    InvestigationStatus,
)
from vigil.services.exporter import ReportExporter, _uri_to_local_path
from vigil.services.telemetry import TelemetryManager
from vigil.storage.repository import InvestigationRepository
from vigil.storage.sqlite_repository import SqliteInvestigationRepository
from vigil.tools.base import generate_sha256

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

    # -------------------------------------------------------------------------
    # Phase 5: Human Review & Audit Layer
    # -------------------------------------------------------------------------
    def review_event(
        self,
        investigation_id: str,
        event_id: str,
        status: str,
        reviewer: str,
        notes: str | None = None,
        description: str | None = None,
        event_type: str | None = None,
        start_seconds: float | None = None,
        end_seconds: float | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> tuple[Event, AuditLog]:
        """Record an investigator review decision for a proposed event."""
        self.repository.get_investigation(investigation_id)
        event = self.repository.get_event(event_id)

        valid_statuses = {"proposed", "under_review", "confirmed", "rejected"}
        if status not in valid_statuses:
            raise ValueError(f"Invalid event status '{status}'. Must be one of {valid_statuses}")

        old_status = event.status
        changes: dict[str, Any] = {}
        updates: dict[str, Any] = {
            "status": status,
            "reviewer": reviewer,
            "review_notes": notes,
            "reviewed_at": datetime.now(UTC),
        }

        if old_status != status:
            changes["status"] = {"old": old_status, "new": status}

        if description is not None and description != event.description:
            changes["description"] = {"old": event.description, "new": description}
            updates["description"] = description

        if event_type is not None and event_type != event.event_type:
            changes["event_type"] = {"old": event.event_type, "new": event_type}
            updates["event_type"] = event_type

        if start_seconds is not None and start_seconds != event.start_seconds:
            changes["start_seconds"] = {"old": event.start_seconds, "new": start_seconds}
            updates["start_seconds"] = start_seconds

        if end_seconds is not None and end_seconds != event.end_seconds:
            changes["end_seconds"] = {"old": event.end_seconds, "new": end_seconds}
            updates["end_seconds"] = end_seconds

        if start_time is not None and start_time != event.start_time:
            changes["start_time"] = {"old": event.start_time.isoformat() if event.start_time else None, "new": start_time.isoformat()}
            updates["start_time"] = start_time

        if end_time is not None and end_time != event.end_time:
            changes["end_time"] = {"old": event.end_time.isoformat() if event.end_time else None, "new": end_time.isoformat()}
            updates["end_time"] = end_time

        updated_event = event.model_copy(update=updates)
        self.repository.add_event(updated_event)

        audit_id = f"audit-{uuid.uuid4().hex[:8]}"
        audit_log = AuditLog(
            audit_id=audit_id,
            investigation_id=investigation_id,
            action="event_review",
            actor=reviewer,
            target_type="event",
            target_id=event_id,
            changes=changes,
            notes=notes,
            metadata={"status": status, "reviewer": reviewer},
        )
        self.repository.add_audit_log(audit_log)

        self.telemetry.broadcast(
            investigation_id=investigation_id,
            event_type="event_reviewed",
            data={
                "event_id": event_id,
                "status": status,
                "reviewer": reviewer,
                "audit_id": audit_id,
            },
        )

        return updated_event, audit_log

    def edit_event(
        self,
        investigation_id: str,
        event_id: str,
        editor: str,
        updates: dict[str, Any],
        notes: str | None = None,
    ) -> tuple[Event, AuditLog]:
        """Directly update event properties with audit trail tracking."""
        self.repository.get_investigation(investigation_id)
        event = self.repository.get_event(event_id)

        changes: dict[str, Any] = {}
        cleaned_updates: dict[str, Any] = {}
        for k, v in updates.items():
            if hasattr(event, k):
                old_val = getattr(event, k)
                if old_val != v:
                    changes[k] = {"old": old_val, "new": v}
                    cleaned_updates[k] = v

        cleaned_updates["reviewer"] = editor
        cleaned_updates["reviewed_at"] = datetime.now(UTC)
        if notes:
            cleaned_updates["review_notes"] = notes

        updated_event = event.model_copy(update=cleaned_updates)
        self.repository.add_event(updated_event)

        audit_id = f"audit-{uuid.uuid4().hex[:8]}"
        audit_log = AuditLog(
            audit_id=audit_id,
            investigation_id=investigation_id,
            action="event_edit",
            actor=editor,
            target_type="event",
            target_id=event_id,
            changes=changes,
            notes=notes,
        )
        self.repository.add_audit_log(audit_log)

        self.telemetry.broadcast(
            investigation_id=investigation_id,
            event_type="event_edited",
            data={
                "event_id": event_id,
                "editor": editor,
                "changes": changes,
                "audit_id": audit_id,
            },
        )

        return updated_event, audit_log

    def get_audit_logs(
        self,
        investigation_id: str,
        target_id: str | None = None,
        actor: str | None = None,
        action: str | None = None,
    ) -> list[AuditLog]:
        """Fetch audit log history for an investigation."""
        self.repository.get_investigation(investigation_id)
        logs = self.repository.list_audit_logs(investigation_id=investigation_id, target_id=target_id)
        if actor:
            logs = [l for l in logs if l.actor == actor]
        if action:
            logs = [l for l in logs if l.action == action]
        return logs

    def slice_incident_clip(
        self,
        investigation_id: str,
        event_id: str,
        padding_seconds: float = 1.0,
    ) -> Artifact:
        """Cut or produce a playable incident sub-clip for an event."""
        self.repository.get_investigation(investigation_id)
        event = self.repository.get_event(event_id)

        media_id: str | None = None
        start_s: float = 0.0
        end_s: float = 5.0

        if event.start_seconds is not None:
            start_s = event.start_seconds
        if event.end_seconds is not None:
            end_s = event.end_seconds

        if event.observation_ids:
            for oid in event.observation_ids:
                try:
                    obs = self.repository.get_observation(oid)
                    if obs.source_references:
                        sr = obs.source_references[0]
                        media_id = sr.media_asset_id
                        if event.start_seconds is None and sr.start_seconds is not None:
                            start_s = sr.start_seconds
                        if event.end_seconds is None and sr.end_seconds is not None:
                            end_s = sr.end_seconds
                        break
                except Exception:  # noqa: BLE001, S110
                    pass

        if not media_id:
            inv = self.repository.get_investigation(investigation_id)
            if inv.media_asset_ids:
                media_id = inv.media_asset_ids[0]
            else:
                raise ValueError("No media asset available for clip cutting.")

        media_asset = self.repository.get_media_asset(media_id)
        clip_dir = self.storage_dir / "clips" / investigation_id
        clip_dir.mkdir(parents=True, exist_ok=True)

        art_id = f"clip-{event_id}-{uuid.uuid4().hex[:6]}"
        clip_file = clip_dir / f"{event_id}_{int(start_s)}_{int(end_s)}.mp4"

        local_file = _uri_to_local_path(media_asset.storage_uri)
        if local_file and local_file.is_file():
            result = ClipSlicer.slice_clip(
                source_path=local_file,
                output_path=clip_file,
                start_seconds=start_s,
                end_seconds=end_s,
                padding_seconds=padding_seconds,
            )
            clip_uri = result.storage_uri
            clip_sha = result.sha256
        else:
            clip_uri = clip_file.as_uri()
            clip_sha = generate_sha256(f"{art_id}:{clip_uri}:{start_s}:{end_s}")

        artifact = Artifact(
            artifact_id=art_id,
            artifact_type="clip",
            media_type="video",
            storage_uri=clip_uri,
            source_reference=SourceReference(
                media_asset_id=media_id,
                start_seconds=start_s,
                end_seconds=end_s,
            ),
            sha256=clip_sha,
        )
        self.repository.add_artifact(artifact)
        return artifact

    def finalize_report(
        self,
        investigation_id: str,
        finalized_by: str,
        title: str | None = None,
        summary: str | None = None,
        notes: str | None = None,
        auto_slice_clips: bool = True,
    ) -> tuple[Report, AuditLog]:
        """Finalize the investigation report, linking confirmed event clips and incrementing report version."""
        inv = self.repository.get_investigation(investigation_id)
        state = self.repository.get_state(investigation_id)
        if state is None:
            raise ValueError(f"Investigation '{investigation_id}' has no execution state.")

        existing_reports = self.repository.list_reports(investigation_id)
        version = len(existing_reports) + 1

        events = self.get_events(investigation_id)
        confirmed_events = [e for e in events if e.status == "confirmed"]
        rejected_events = [e for e in events if e.status == "rejected"]
        proposed_events = [e for e in events if e.status in {"proposed", "under_review"}]

        clip_ids: list[str] = []
        if auto_slice_clips:
            existing_clips = [a for a in self.get_artifacts(investigation_id) if a.artifact_type in {"clip", "subclip", "video_clip"}]
            existing_clip_ids = {c.artifact_id for c in existing_clips}
            clip_ids.extend(list(existing_clip_ids))

            for ce in confirmed_events:
                has_clip = any(
                    c.source_reference.start_seconds == ce.start_seconds
                    and c.source_reference.end_seconds == ce.end_seconds
                    for c in existing_clips
                )
                if not has_clip:
                    try:
                        clip_art = self.slice_incident_clip(investigation_id, ce.event_id)
                        clip_ids.append(clip_art.artifact_id)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(f"Could not slice clip for event {ce.event_id}: {exc}")

        if not summary:
            prev_summary = existing_reports[-1].summary if existing_reports else ""
            summary = (
                f"{prev_summary}\n\n"
                f"**Final Human Review Findings**: Investigation reviewed and finalized by {finalized_by}. "
                f"A total of {len(events)} events were evaluated: {len(confirmed_events)} confirmed, "
                f"{len(rejected_events)} rejected, and {len(proposed_events)} pending review."
            ).strip()

        rep_title = title or f"Final Forensic Investigation Report - {inv.title} (v{version})"
        report_id = f"rep-fin-{uuid.uuid4().hex[:8]}"

        coverages = self.get_coverage_records(investigation_id)
        assessments = self.repository.list_evidence_assessments()

        final_report = Report(
            report_id=report_id,
            investigation_id=investigation_id,
            title=rep_title,
            summary=summary,
            observation_ids=state.observation_ids,
            event_ids=[e.event_id for e in events],
            assessment_ids=[a.assessment_id for a in assessments],
            coverage_ids=[c.coverage_id for c in coverages],
            version=version,
            status="finalized",
            clip_artifact_ids=list(dict.fromkeys(clip_ids)),
            notes=notes,
            finalized_at=datetime.now(UTC),
            finalized_by=finalized_by,
            generated_by=finalized_by,
        )
        self.repository.add_report(final_report)

        audit_id = f"audit-{uuid.uuid4().hex[:8]}"
        audit_log = AuditLog(
            audit_id=audit_id,
            investigation_id=investigation_id,
            action="report_finalize",
            actor=finalized_by,
            target_type="report",
            target_id=report_id,
            changes={"version": {"old": version - 1, "new": version}, "status": {"old": "draft", "new": "finalized"}},
            notes=notes,
            metadata={
                "confirmed_events": len(confirmed_events),
                "rejected_events": len(rejected_events),
                "clip_count": len(clip_ids),
            },
        )
        self.repository.add_audit_log(audit_log)

        self.telemetry.broadcast(
            investigation_id=investigation_id,
            event_type="report_finalized",
            data={
                "report_id": report_id,
                "version": version,
                "finalized_by": finalized_by,
                "audit_id": audit_id,
            },
        )

        return final_report, audit_log

    def export_report_html(
        self,
        investigation_id: str,
        report_id: str | None = None,
        base_url: str = "",
    ) -> str:
        """Render complete forensic report as interactive HTML."""
        inv = self.get_investigation(investigation_id)
        report = self.repository.get_report(report_id) if report_id else self.get_report(investigation_id)
        if report is None:
            raise ValueError(f"No report available for investigation '{investigation_id}'.")

        events = self.get_events(investigation_id)
        obs = self.get_observations(investigation_id)
        coverages = self.get_coverage_records(investigation_id)
        artifacts = self.get_artifacts(investigation_id)
        assessments = self.repository.list_evidence_assessments()
        audit_logs = self.get_audit_logs(investigation_id)
        media_assets = [self.repository.get_media_asset(mid) for mid in inv.media_asset_ids if mid in [m.media_asset_id for m in self.repository.list_media_assets()]]

        return ReportExporter.export_html(
            investigation=inv,
            report=report,
            events=events,
            observations=obs,
            assessments=assessments,
            coverages=coverages,
            artifacts=artifacts,
            audit_logs=audit_logs,
            media_assets=media_assets,
            base_url=base_url,
        )

    def export_report_pdf(
        self,
        investigation_id: str,
        report_id: str | None = None,
    ) -> bytes:
        """Render publication-grade forensic report as PDF binary."""
        inv = self.get_investigation(investigation_id)
        report = self.repository.get_report(report_id) if report_id else self.get_report(investigation_id)
        if report is None:
            raise ValueError(f"No report available for investigation '{investigation_id}'.")

        events = self.get_events(investigation_id)
        obs = self.get_observations(investigation_id)
        coverages = self.get_coverage_records(investigation_id)
        artifacts = self.get_artifacts(investigation_id)
        assessments = self.repository.list_evidence_assessments()
        audit_logs = self.get_audit_logs(investigation_id)
        media_assets = [self.repository.get_media_asset(mid) for mid in inv.media_asset_ids if mid in [m.media_asset_id for m in self.repository.list_media_assets()]]

        return ReportExporter.export_pdf(
            investigation=inv,
            report=report,
            events=events,
            observations=obs,
            assessments=assessments,
            coverages=coverages,
            artifacts=artifacts,
            audit_logs=audit_logs,
            media_assets=media_assets,
        )

    def get_artifact_content_path(self, artifact_id: str) -> Path | None:
        """Resolve artifact local disk path if it exists."""
        artifact = self.repository.get_artifact(artifact_id)
        return _uri_to_local_path(artifact.storage_uri)


    def get_media_assets(self, investigation_id: str) -> list[MediaAsset]:
        """Retrieve media assets associated with an investigation."""
        inv = self.get_investigation(investigation_id)
        all_assets = {m.media_asset_id: m for m in self.repository.list_media_assets()}
        return [all_assets[mid] for mid in inv.media_asset_ids if mid in all_assets]

    def get_media_asset_content_path(self, media_asset_id: str) -> Path | None:
        """Resolve media asset local disk path if it exists."""
        media_asset = self.repository.get_media_asset(media_asset_id)
        return _uri_to_local_path(media_asset.storage_uri)

    def get_evidence_assessments(self, investigation_id: str) -> list[EvidenceAssessment]:
        """Retrieve evidence assessments related to an investigation."""
        self.get_investigation(investigation_id)
        events = self.get_events(investigation_id)
        obs = self.get_observations(investigation_id)
        target_ids = {e.event_id for e in events} | {o.observation_id for o in obs}
        all_assessments = self.repository.list_evidence_assessments()
        filtered = [a for a in all_assessments if a.target_id in target_ids]
        return filtered if filtered or not all_assessments else all_assessments

    def create_demo_investigation(self) -> tuple[Investigation, IngestionResult]:
        """Seed a realistic forensic investigation with synthetic footage, frames, observations, and events."""
        import math

        import av
        import numpy as np

        demo_dir = self.storage_dir / "demo"
        demo_dir.mkdir(parents=True, exist_ok=True)
        video_path = demo_dir / "demo_perimeter_feed.mp4"

        # Generate 6-second surveillance footage with timecode and crosshairs
        fps = 24
        duration_seconds = 6.0
        width = 640
        height = 360
        total_frames = int(duration_seconds * fps)

        with av.open(str(video_path), mode="w", format="mp4") as container:
            v_stream = container.add_stream("h264", rate=fps)
            v_stream.width = width
            v_stream.height = height
            v_stream.pix_fmt = "yuv420p"

            a_stream = None
            try:
                a_stream = container.add_stream("aac", rate=44100)
                a_stream.format = "fltp"
                a_stream.layout = "stereo"
            except Exception:  # noqa: BLE001, S110
                pass

            for i in range(total_frames):
                t_sec = i / fps
                img = np.zeros((height, width, 3), dtype=np.uint8)
                # CCTV dark night surveillance aesthetic
                img[:, :, :] = 18
                # Ground grid lines
                for y in range(180, height, 30):
                    img[y, :, :] = 35
                for x in range(0, width, 50):
                    img[180:, x, :] = 35

                # Security perimeter fence line (yellow/amber warning stripe)
                img[175:180, :, 0] = 0
                img[175:180, :, 1] = 180
                img[175:180, :, 2] = 230

                # Simulated intruder moving between t=1.0s and t=4.5s
                if 1.0 <= t_sec <= 4.5:
                    prog = (t_sec - 1.0) / 3.5
                    px = int(120 + prog * 400)
                    py = int(160 - math.sin(prog * math.pi) * 20)
                    img[py:py+50, px:px+20, 0] = 220
                    img[py:py+50, px:px+20, 1] = 220
                    img[py:py+50, px:px+20, 2] = 220

                frame = av.VideoFrame.from_ndarray(img, format="bgr24")
                for packet in v_stream.encode(frame):
                    container.mux(packet)

            if a_stream is not None:
                num_samples = int(duration_seconds * 44100)
                t = np.linspace(0, duration_seconds, num_samples, dtype=np.float32)
                rumble = np.sin(2 * math.pi * 60 * t) * 0.1
                alert = np.where((t >= 2.4) & (t <= 2.9), np.sin(2 * math.pi * 880 * t) * 0.4, 0.0)
                audio = (rumble + alert).astype(np.float32)
                stereo = np.stack([audio, audio])
                a_frame = av.AudioFrame.from_ndarray(stereo, format="fltp", layout="stereo")
                a_frame.rate = 44100
                for packet in a_stream.encode(a_frame):
                    container.mux(packet)
                for packet in a_stream.encode():
                    container.mux(packet)

            for packet in v_stream.encode():
                container.mux(packet)

        # Ingest the generated video
        inv_id = f"inv-demo-{uuid.uuid4().hex[:6]}"
        inv, result = self.create_and_ingest_investigation(
            file_path=video_path,
            investigation_id=inv_id,
            title="Operation Nightwatch: North Perimeter Intrusion Analysis",
            objective="Identify unauthorized boundary breaches, classify acoustic anomalies, and correlate suspect trajectory.",
            scope_description="Continuous PTZ surveillance footage from North Gate Sector 4",
            camera_id="cam-north-04",
            camera_name="North Perimeter PTZ Cam 04",
            camera_location="Perimeter Sector 4 (North Border)",
            camera_timezone="UTC",
            sample_interval_seconds=1.0,
            max_frames=6,
            extract_audio=True,
            created_by="Lead Det. Vance",
        )

        prov_vis = Provenance(
            producer_type="vision_model",
            producer_name="YOLOv8x-Forensic",
            method="object_detection",
        )
        prov_aud = Provenance(
            producer_type="audio_model",
            producer_name="Whisper-Acoustic-V3",
            method="audio_transcription",
        )

        src_ref1 = SourceReference(media_asset_id=result.media_asset.media_asset_id, start_seconds=1.2, end_seconds=2.6)
        obs1 = Observation(
            observation_id=f"obs-{uuid.uuid4().hex[:6]}",
            modality="video",
            observation_type="person_detection",
            description="Individual dressed in dark tactical gear approaching the perimeter boundary.",
            source_references=[src_ref1],
            confidence=0.96,
            provenance=prov_vis,
        )
        self.repository.add_observation(obs1)

        src_ref2 = SourceReference(media_asset_id=result.media_asset.media_asset_id, start_seconds=2.4, end_seconds=2.9)
        obs2 = Observation(
            observation_id=f"obs-{uuid.uuid4().hex[:6]}",
            modality="audio",
            observation_type="acoustic_transient",
            description="High-frequency acoustic transient (880 Hz harmonic spike) matching gate latch tamper sound.",
            source_references=[src_ref2],
            confidence=0.89,
            provenance=prov_aud,
        )
        self.repository.add_observation(obs2)

        src_ref3 = SourceReference(media_asset_id=result.media_asset.media_asset_id, start_seconds=3.2, end_seconds=4.4)
        obs3 = Observation(
            observation_id=f"obs-{uuid.uuid4().hex[:6]}",
            modality="video",
            observation_type="motion_detected",
            description="Rapid lateral traversal across marked yellow restricted security zone.",
            source_references=[src_ref3],
            confidence=0.93,
            provenance=prov_vis,
        )
        self.repository.add_observation(obs3)

        evt1 = Event(
            event_id=f"evt-{uuid.uuid4().hex[:6]}",
            event_type="restricted_boundary_crossing",
            description="Subject crosses perimeter yellow line into restricted facility corridor.",
            observation_ids=[obs1.observation_id, obs3.observation_id],
            status="confirmed",
            start_seconds=1.2,
            end_seconds=3.5,
            reviewer="Lead Det. Vance",
            review_notes="Verified against ground boundary coordinates. Movement speed indicates deliberate penetration.",
            reviewed_at=datetime.now(UTC),
        )
        self.repository.add_event(evt1)

        evt2 = Event(
            event_id=f"evt-{uuid.uuid4().hex[:6]}",
            event_type="security_hardware_tamper",
            description="Acoustic signature of manual gate lock vibration and hardware manipulation.",
            observation_ids=[obs2.observation_id],
            status="proposed",
            start_seconds=2.3,
            end_seconds=3.1,
        )
        self.repository.add_event(evt2)

        evt3 = Event(
            event_id=f"evt-{uuid.uuid4().hex[:6]}",
            event_type="secondary_zone_incursion",
            description="Subject sprints toward inner building entrance.",
            observation_ids=[obs3.observation_id],
            status="under_review",
            start_seconds=3.6,
            end_seconds=4.5,
            reviewer="Analyst Chen",
            review_notes="Cross-referencing with building interior door sensor logs.",
            reviewed_at=datetime.now(UTC),
        )
        self.repository.add_event(evt3)

        as1 = EvidenceAssessment(
            assessment_id=f"assess-{uuid.uuid4().hex[:6]}",
            target_type="event",
            target_id=evt1.event_id,
            assessment_type="evidence_quality",
            rating="high",
            rationale="Clear multi-frame visual detection with high confidence (0.96) and uninterrupted track.",
            assessed_by="Automated Verification Agent",
        )
        as2 = EvidenceAssessment(
            assessment_id=f"assess-{uuid.uuid4().hex[:6]}",
            target_type="event",
            target_id=evt2.event_id,
            assessment_type="uncertainty",
            rating="moderate",
            rationale="Acoustic harmonic matches latch strike; however, physical contact is partially occluded.",
            assessed_by="Temporal Correlator Agent",
        )
        as3 = EvidenceAssessment(
            assessment_id=f"assess-{uuid.uuid4().hex[:6]}",
            target_type="observation",
            target_id=obs2.observation_id,
            assessment_type="support_level",
            rating="high",
            rationale="Clean spectral peak at 880Hz with 18dB SNR over background rumble.",
            assessed_by="Acoustic Signal Assessor",
        )
        self.repository.add_evidence_assessment(as1)
        self.repository.add_evidence_assessment(as2)
        self.repository.add_evidence_assessment(as3)

        try:
            self.slice_incident_clip(inv.investigation_id, evt1.event_id, padding_seconds=0.5)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Could not auto-slice demo clip: {exc}")

        rep = Report(
            report_id=f"rep-{uuid.uuid4().hex[:6]}",
            investigation_id=inv.investigation_id,
            title="Preliminary Forensic Report: North Perimeter Gate Breach",
            summary=(
                "Autonomous multi-modal forensic analysis confirms an unauthorized restricted boundary breach "
                "at 00:01.20 - 00:03.50 into Sector 4 corridor. Acoustic telemetry detected simultaneous gate hardware "
                "manipulation at 00:02.40. One incident sub-clip has been isolated and cryptographically indexed."
            ),
            observation_ids=[obs1.observation_id, obs2.observation_id, obs3.observation_id],
            event_ids=[evt1.event_id, evt2.event_id, evt3.event_id],
            assessment_ids=[as1.assessment_id, as2.assessment_id, as3.assessment_id],
            generated_by="Agentic Reporter & Synthesizer",
            version=1,
            status="draft",
        )
        self.repository.add_report(rep)

        st = InvestigationState(
            investigation_id=inv.investigation_id,
            status=InvestigationStatus.COMPLETED,
            completed_at=datetime.now(UTC),
            task_ids=["task-ingest", "task-visual", "task-audio", "task-temporal", "task-verify", "task-report"],
            observation_ids=[obs1.observation_id, obs2.observation_id, obs3.observation_id],
            event_ids=[evt1.event_id, evt2.event_id, evt3.event_id],
        )
        self.repository.save_state(st)

        audit = AuditLog(
            audit_id=f"audit-{uuid.uuid4().hex[:8]}",
            investigation_id=inv.investigation_id,
            action="investigation_update",
            actor="Lead Det. Vance",
            target_type="investigation",
            target_id=inv.investigation_id,
            notes="Demo case initialized with multi-modal forensic pipeline.",
        )
        self.repository.add_audit_log(audit)

        return inv, result
