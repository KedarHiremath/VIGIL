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
from vigil.domain.event_link import EventLink
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
        file_path: Path | str | None = None,
        file_paths: list[Path | str] | None = None,
        investigation_id: str | None = None,
        title: str | None = None,
        objective: str | None = None,
        scope_description: str | None = None,
        camera_id: str | None = None,
        camera_ids: list[str] | None = None,
        camera_name: str | None = None,
        camera_location: str | None = None,
        camera_timezone: str | None = None,
        sample_interval_seconds: float = 2.0,
        max_frames: int = 50,
        extract_audio: bool = True,
        created_by: str | None = None,
    ) -> tuple[Investigation, IngestionResult]:
        """Ingest one or more physical media files sequentially, register assets, and create Investigation."""
        inv_id = investigation_id or f"inv-{uuid.uuid4().hex[:8]}"

        # Resolve paths
        target_paths: list[Path] = []
        if file_paths:
            for p in file_paths:
                resolved = Path(p).resolve()
                if not resolved.is_file():
                    raise FileNotFoundError(f"Source media file not found: {resolved}")
                target_paths.append(resolved)
        elif file_path:
            resolved = Path(file_path).resolve()
            if not resolved.is_file():
                raise FileNotFoundError(f"Source media file not found: {resolved}")
            target_paths.append(resolved)
        else:
            raise FileNotFoundError("At least one media file_path or file_paths must be specified.")

        artifacts_dir = self.storage_dir / "artifacts" / inv_id
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Ingest each media file sequentially (following existing architecture)
        ingestion_results: list[IngestionResult] = []
        for idx, path in enumerate(target_paths):
            if camera_ids and idx < len(camera_ids) and camera_ids[idx]:
                curr_cam_id: str | None = camera_ids[idx]
            elif camera_id:
                curr_cam_id = camera_id if len(target_paths) == 1 else f"{camera_id}-{idx+1:02d}"
            else:
                curr_cam_id = f"cam-{idx+1:02d}"

            curr_cam_name = (
                f"{camera_name} (Feed {idx+1})"
                if camera_name and len(target_paths) > 1
                else (camera_name or f"Camera {curr_cam_id}")
            )

            res = self.media_service.ingest_file(
                file_path=path,
                camera_id=curr_cam_id,
                camera_name=curr_cam_name,
                camera_location=camera_location,
                camera_timezone=camera_timezone,
                sample_interval_seconds=sample_interval_seconds,
                max_frames=max_frames,
                extract_audio=extract_audio,
                output_artifacts_dir=artifacts_dir,
            )
            ingestion_results.append(res)

        primary_result = IngestionResult(
            media_asset=ingestion_results[0].media_asset,
            camera=ingestion_results[0].camera,
            frame_artifacts=ingestion_results[0].frame_artifacts,
            audio_artifacts=ingestion_results[0].audio_artifacts,
            additional_results=ingestion_results[1:],
        )

        # Build investigation domain model
        if len(target_paths) > 1:
            inv_title = title or f"Investigation: Multi-Camera Premise ({len(target_paths)} feeds)"
            inv_scope = (
                scope_description
                or f"Multi-video forensic surveillance examination covering premise across {len(target_paths)} camera feeds"
            )
        else:
            inv_title = title or f"Investigation: {target_paths[0].name}"
            inv_scope = scope_description or f"Physical media footage analysis from {target_paths[0].name}"

        inv_objective = (
            objective or "Perform comprehensive forensic video and audio examination."
        )

        all_media_ids = [res.media_asset.media_asset_id for res in ingestion_results]

        investigation = Investigation(
            investigation_id=inv_id,
            title=inv_title,
            objective=inv_objective,
            scope_description=inv_scope,
            media_asset_ids=all_media_ids,
            created_by=created_by or "vigil-api-user",
        )
        self.repository.add_investigation(investigation)

        # Initialize state
        initial_state = InvestigationState(
            investigation_id=inv_id,
            status=InvestigationStatus.CREATED,
        )
        self.repository.save_state(initial_state)

        total_frames = sum(len(r.frame_artifacts) for r in ingestion_results)
        any_audio = any(len(r.audio_artifacts) > 0 for r in ingestion_results)
        cam_ids = [r.camera.camera_id for r in ingestion_results if r.camera]

        # Broadcast creation event
        self.telemetry.broadcast(
            investigation_id=inv_id,
            event_type="investigation_created",
            data={
                "investigation_id": inv_id,
                "title": inv_title,
                "media_asset_id": primary_result.media_asset.media_asset_id,
                "media_asset_ids": all_media_ids,
                "media_count": len(all_media_ids),
                "camera_ids": cam_ids,
                "frame_count": total_frames,
                "has_audio": any_audio,
            },
        )

        return investigation, primary_result

    def add_and_ingest_media(
        self,
        investigation_id: str,
        file_path: Path | str,
        camera_id: str | None = None,
        camera_name: str | None = None,
        camera_location: str | None = None,
        camera_timezone: str | None = None,
        sample_interval_seconds: float = 2.0,
        max_frames: int = 50,
        extract_audio: bool = True,
    ) -> IngestionResult:
        """Add and ingest an additional video feed into an existing investigation."""
        inv = self.repository.get_investigation(investigation_id)
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Source media file not found: {path}")

        artifacts_dir = self.storage_dir / "artifacts" / investigation_id
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        curr_cam_id = camera_id or f"cam-{len(inv.media_asset_ids) + 1:02d}"
        res = self.media_service.ingest_file(
            file_path=path,
            camera_id=curr_cam_id,
            camera_name=camera_name or f"Camera {curr_cam_id}",
            camera_location=camera_location,
            camera_timezone=camera_timezone,
            sample_interval_seconds=sample_interval_seconds,
            max_frames=max_frames,
            extract_audio=extract_audio,
            output_artifacts_dir=artifacts_dir,
        )

        updated_media_ids = list(inv.media_asset_ids) + [res.media_asset.media_asset_id]
        updated_inv = Investigation(
            investigation_id=inv.investigation_id,
            title=inv.title,
            objective=inv.objective,
            scope_description=inv.scope_description,
            media_asset_ids=updated_media_ids,
            source_reference_ids=inv.source_reference_ids,
            created_at=inv.created_at,
            created_by=inv.created_by,
        )
        self.repository.add_investigation(updated_inv)

        self.telemetry.broadcast(
            investigation_id=investigation_id,
            event_type="media_added",
            data={
                "investigation_id": investigation_id,
                "media_asset_id": res.media_asset.media_asset_id,
                "camera_id": curr_cam_id,
                "frame_count": len(res.frame_artifacts),
                "total_media_count": len(updated_media_ids),
            },
        )
        return res

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
            if a.source_reference and a.source_reference.media_asset_id in inv_asset_ids
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
                f"A total of {len(events)} events were evaluated across premise feeds: {len(confirmed_events)} confirmed, "
                f"{len(rejected_events)} rejected, and {len(proposed_events)} pending review."
            ).strip()

        rep_title = title or f"Final Forensic Investigation Report - {inv.title} (v{version})"
        report_id = f"rep-fin-{uuid.uuid4().hex[:8]}"

        coverages = self.get_coverage_records(investigation_id)
        assessments = self.get_evidence_assessments(investigation_id)

        visual_evidence: list[dict[str, Any]] = []
        evidence_frame_ids: list[str] = []
        if existing_reports:
            last_rep = existing_reports[-1]
            visual_evidence = list(getattr(last_rep, "visual_evidence", []))
            evidence_frame_ids = list(getattr(last_rep, "evidence_frame_artifact_ids", []))

        if not visual_evidence:
            try:
                from vigil.tools.visual_annotator import VisualEvidenceAnnotator
                annotator = VisualEvidenceAnnotator(
                    repository=self.repository,
                    llm_client=getattr(self.orchestrator, "llm", None),
                    storage_dir=self.storage_dir,
                )
                evidence_objs = annotator.prepare_visual_evidence(investigation_id, max_frames=3)
                for item in evidence_objs:
                    visual_evidence.append(item.model_dump())
                    evidence_frame_ids.append(item.artifact_id)
            except Exception as exc:
                logger.warning("finalize_report: Visual evidence preparation fallback failed: %s", exc)

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
            evidence_frame_artifact_ids=evidence_frame_ids,
            visual_evidence=visual_evidence,
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
        assessments = self.get_evidence_assessments(investigation_id)
        audit_logs = self.get_audit_logs(investigation_id)
        all_assets = {m.media_asset_id: m for m in self.repository.list_media_assets()}
        media_assets = [all_assets[mid] for mid in inv.media_asset_ids if mid in all_assets]

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
        assessments = self.get_evidence_assessments(investigation_id)
        audit_logs = self.get_audit_logs(investigation_id)
        all_assets = {m.media_asset_id: m for m in self.repository.list_media_assets()}
        media_assets = [all_assets[mid] for mid in inv.media_asset_ids if mid in all_assets]

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
        """Retrieve evidence assessments strictly related to an investigation."""
        self.get_investigation(investigation_id)
        events = self.get_events(investigation_id)
        obs = self.get_observations(investigation_id)
        target_ids = {e.event_id for e in events} | {o.observation_id for o in obs}
        all_assessments = self.repository.list_evidence_assessments()
        return [a for a in all_assessments if a.target_id in target_ids]

    def export_report_markdown(
        self,
        investigation_id: str,
        report_id: str | None = None,
    ) -> str:
        """Render complete forensic report as structured, timestamp-based Markdown deliverable."""
        inv = self.get_investigation(investigation_id)
        report = self.repository.get_report(report_id) if report_id else self.get_report(investigation_id)
        if report is None:
            raise ValueError(f"No report available for investigation '{investigation_id}'.")

        events = self.get_events(investigation_id)
        obs = self.get_observations(investigation_id)
        coverages = self.get_coverage_records(investigation_id)
        artifacts = self.get_artifacts(investigation_id)
        assessments = self.get_evidence_assessments(investigation_id)
        audit_logs = self.get_audit_logs(investigation_id)
        all_assets = {m.media_asset_id: m for m in self.repository.list_media_assets()}
        media_assets = [all_assets[mid] for mid in inv.media_asset_ids if mid in all_assets]

        return ReportExporter.export_markdown(
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

    def create_demo_investigation(self) -> tuple[Investigation, IngestionResult]:
        """Seed a realistic multi-camera forensic case with two synchronized feeds covering the same premise."""
        import math

        import av
        import numpy as np

        demo_dir = self.storage_dir / "demo"
        demo_dir.mkdir(parents=True, exist_ok=True)
        video1_path = demo_dir / "demo_north_gate_feed.mp4"
        video2_path = demo_dir / "demo_courtyard_feed.mp4"

        fps = 24
        duration_seconds = 6.0
        width = 640
        height = 360
        total_frames = int(duration_seconds * fps)

        # -------------------------------------------------------------
        # Generate Feed 1: North Perimeter Entrance Gate (cam-north-04)
        # -------------------------------------------------------------
        with av.open(str(video1_path), mode="w", format="mp4") as container:
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
                img[:, :, :] = 18
                for y in range(180, height, 30):
                    img[y, :, :] = 35
                for x in range(0, width, 50):
                    img[180:, x, :] = 35

                # North Gate perimeter fence line (amber/yellow stripe)
                img[175:180, :, 0] = 0
                img[175:180, :, 1] = 180
                img[175:180, :, 2] = 230

                # Suspect approaches gate (t=1.0 to 4.2s)
                if 1.0 <= t_sec <= 4.2:
                    prog = (t_sec - 1.0) / 3.2
                    px = int(100 + prog * 420)
                    py = int(160 - math.sin(prog * math.pi) * 18)
                    img[py:py+50, px:px+20, :] = 220

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

        # -------------------------------------------------------------
        # Generate Feed 2: Central Facility Courtyard (cam-courtyard-02)
        # -------------------------------------------------------------
        with av.open(str(video2_path), mode="w", format="mp4") as container:
            v_stream2 = container.add_stream("h264", rate=fps)
            v_stream2.width = width
            v_stream2.height = height
            v_stream2.pix_fmt = "yuv420p"

            a_stream2 = None
            try:
                a_stream2 = container.add_stream("aac", rate=44100)
                a_stream2.format = "fltp"
                a_stream2.layout = "stereo"
            except Exception:  # noqa: BLE001, S110
                pass

            for i in range(total_frames):
                t_sec = i / fps
                img = np.zeros((height, width, 3), dtype=np.uint8)
                img[:, :, :] = 22
                # Courtyard floor grid (blue tinted courtyard stone)
                for y in range(160, height, 25):
                    img[y, :, 0] = 50
                    img[y, :, 1] = 40
                    img[y, :, 2] = 30
                # Building entrance structure on right
                img[130:260, 480:540, :] = 60
                img[150:240, 500:525, 0] = 120
                img[150:240, 500:525, 1] = 90

                # Suspect emerges from north gate corridor at t=3.5s and crosses courtyard
                if 3.5 <= t_sec <= 5.8:
                    prog2 = (t_sec - 3.5) / 2.3
                    px = int(80 + prog2 * 410)
                    py = int(180 - math.sin(prog2 * math.pi) * 12)
                    img[py:py+48, px:px+20, :] = 220

                frame = av.VideoFrame.from_ndarray(img, format="bgr24")
                for packet in v_stream2.encode(frame):
                    container.mux(packet)

            if a_stream2 is not None:
                num_samples = int(duration_seconds * 44100)
                t = np.linspace(0, duration_seconds, num_samples, dtype=np.float32)
                courtyard_hum = np.sin(2 * math.pi * 120 * t) * 0.05
                footsteps = np.where((t >= 4.0) & (t <= 4.6), np.sin(2 * math.pi * 300 * t) * 0.25, 0.0)
                audio = (courtyard_hum + footsteps).astype(np.float32)
                stereo = np.stack([audio, audio])
                a_frame = av.AudioFrame.from_ndarray(stereo, format="fltp", layout="stereo")
                a_frame.rate = 44100
                for packet in a_stream2.encode(a_frame):
                    container.mux(packet)
                for packet in a_stream2.encode():
                    container.mux(packet)

            for packet in v_stream2.encode():
                container.mux(packet)

        # -------------------------------------------------------------
        # Sequential Ingestion of Both Feeds into Unified Investigation
        # -------------------------------------------------------------
        inv_id = f"inv-demo-{uuid.uuid4().hex[:6]}"
        inv, primary_result = self.create_and_ingest_investigation(
            file_paths=[video1_path, video2_path],
            investigation_id=inv_id,
            title="Operation Nightwatch: North Perimeter & Courtyard Breach",
            objective="Correlate unauthorized boundary breach across North Gate and Central Courtyard feeds, classify acoustic anomalies, and track suspect trajectory across premise.",
            scope_description="Synchronized multi-camera CCTV feeds: North Perimeter Gate (cam-north-04) and Central Facility Courtyard (cam-courtyard-02)",
            camera_ids=["cam-north-04", "cam-courtyard-02"],
            sample_interval_seconds=1.0,
            max_frames=6,
            extract_audio=True,
            created_by="Lead Det. Vance",
        )

        all_results = primary_result.all_ingestion_results
        res1 = all_results[0]
        res2 = all_results[1] if len(all_results) > 1 else all_results[0]

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

        # Observations for Feed 1 (North Gate)
        src_ref1 = SourceReference(media_asset_id=res1.media_asset.media_asset_id, start_seconds=1.2, end_seconds=2.6)
        obs1 = Observation(
            observation_id=f"obs-{uuid.uuid4().hex[:6]}",
            modality="video",
            observation_type="person_detection",
            description="[cam-north-04: North Perimeter Sector 4] Individual dressed in dark tactical gear approaching perimeter boundary.",
            source_references=[src_ref1],
            confidence=0.96,
            provenance=prov_vis,
        )
        self.repository.add_observation(obs1)

        src_ref2 = SourceReference(media_asset_id=res1.media_asset.media_asset_id, start_seconds=2.4, end_seconds=2.9)
        obs2 = Observation(
            observation_id=f"obs-{uuid.uuid4().hex[:6]}",
            modality="audio",
            observation_type="acoustic_transient",
            description="[cam-north-04 Audio] High-frequency acoustic transient (880 Hz harmonic spike) matching gate latch tamper sound.",
            source_references=[src_ref2],
            confidence=0.89,
            provenance=prov_aud,
        )
        self.repository.add_observation(obs2)

        src_ref3 = SourceReference(media_asset_id=res1.media_asset.media_asset_id, start_seconds=3.0, end_seconds=4.2)
        obs3 = Observation(
            observation_id=f"obs-{uuid.uuid4().hex[:6]}",
            modality="video",
            observation_type="motion_detected",
            description="[cam-north-04: North Perimeter Sector 4] Rapid lateral traversal across yellow security boundary into connecting courtyard path.",
            source_references=[src_ref3],
            confidence=0.94,
            provenance=prov_vis,
        )
        self.repository.add_observation(obs3)

        # Observations for Feed 2 (Central Courtyard)
        src_ref4 = SourceReference(media_asset_id=res2.media_asset.media_asset_id, start_seconds=3.6, end_seconds=4.8)
        obs4 = Observation(
            observation_id=f"obs-{uuid.uuid4().hex[:6]}",
            modality="video",
            observation_type="person_detection",
            description="[cam-courtyard-02: Central Facility Courtyard] Subject matching tactical profile emerges from North corridor into inner courtyard.",
            source_references=[src_ref4],
            confidence=0.95,
            provenance=prov_vis,
        )
        self.repository.add_observation(obs4)

        src_ref5 = SourceReference(media_asset_id=res2.media_asset.media_asset_id, start_seconds=4.6, end_seconds=5.8)
        obs5 = Observation(
            observation_id=f"obs-{uuid.uuid4().hex[:6]}",
            modality="video",
            observation_type="motion_detected",
            description="[cam-courtyard-02: Central Facility Courtyard] Subject rapidly advances across courtyard towards building entry door.",
            source_references=[src_ref5],
            confidence=0.92,
            provenance=prov_vis,
        )
        self.repository.add_observation(obs5)

        # Events correlated across both feeds
        evt1 = Event(
            event_id=f"evt-{uuid.uuid4().hex[:6]}",
            event_type="restricted_boundary_crossing",
            description="Subject approaches and crosses North Gate security perimeter line [Camera: cam-north-04].",
            observation_ids=[obs1.observation_id, obs3.observation_id],
            status="confirmed",
            start_seconds=1.2,
            end_seconds=3.5,
            reviewer="Lead Det. Vance",
            review_notes="Verified against ground coordinates. Deliberate boundary penetration confirmed on Feed 1.",
            reviewed_at=datetime.now(UTC),
        )
        self.repository.add_event(evt1)

        evt2 = Event(
            event_id=f"evt-{uuid.uuid4().hex[:6]}",
            event_type="security_hardware_tamper",
            description="Acoustic signature of manual gate lock vibration and hardware manipulation [Camera: cam-north-04].",
            observation_ids=[obs2.observation_id],
            status="proposed",
            start_seconds=2.4,
            end_seconds=3.0,
        )
        self.repository.add_event(evt2)

        evt3 = Event(
            event_id=f"evt-{uuid.uuid4().hex[:6]}",
            event_type="cross_camera_premise_transition",
            description="Suspect transitions from North Gate into Central Facility Courtyard [Correlated across cam-north-04 & cam-courtyard-02].",
            observation_ids=[obs3.observation_id, obs4.observation_id],
            status="confirmed",
            start_seconds=3.2,
            end_seconds=4.6,
            reviewer="Lead Det. Vance",
            review_notes="Cross-camera correlation confirms uninterrupted suspect track moving through North access corridor into courtyard.",
            reviewed_at=datetime.now(UTC),
        )
        self.repository.add_event(evt3)

        evt4 = Event(
            event_id=f"evt-{uuid.uuid4().hex[:6]}",
            event_type="facility_courtyard_incursion",
            description="Unauthorized traversal across Central Facility Courtyard toward secure building entry [Camera: cam-courtyard-02].",
            observation_ids=[obs4.observation_id, obs5.observation_id],
            status="confirmed",
            start_seconds=4.0,
            end_seconds=5.8,
            reviewer="Analyst Chen",
            review_notes="Movement trajectory points directly to secure inner facility door.",
            reviewed_at=datetime.now(UTC),
        )
        self.repository.add_event(evt4)

        # Cross-camera chronological event links
        link1 = EventLink(
            event_link_id=f"link-{uuid.uuid4().hex[:6]}",
            from_event_id=evt1.event_id,
            to_event_id=evt2.event_id,
            relationship_type="overlaps",
            rationale="Acoustic hardware tamper coincides with physical approach to gate boundary.",
            confidence=0.91,
        )
        link2 = EventLink(
            event_link_id=f"link-{uuid.uuid4().hex[:6]}",
            from_event_id=evt1.event_id,
            to_event_id=evt3.event_id,
            relationship_type="before",
            rationale="Suspect breaches North Gate before transitioning into courtyard corridor.",
            confidence=0.95,
        )
        link3 = EventLink(
            event_link_id=f"link-{uuid.uuid4().hex[:6]}",
            from_event_id=evt3.event_id,
            to_event_id=evt4.event_id,
            relationship_type="before",
            rationale="Corridor transition leads directly into courtyard advance.",
            confidence=0.96,
        )
        self.repository.add_event_link(link1)
        self.repository.add_event_link(link2)
        self.repository.add_event_link(link3)

        # Evidence assessments
        as1 = EvidenceAssessment(
            assessment_id=f"assess-{uuid.uuid4().hex[:6]}",
            target_type="event",
            target_id=evt1.event_id,
            assessment_type="evidence_quality",
            rating="high",
            rationale="Clear multi-frame visual detection with high confidence (0.96) and uninterrupted track on cam-north-04.",
            assessed_by="Automated Verification Agent",
        )
        as2 = EvidenceAssessment(
            assessment_id=f"assess-{uuid.uuid4().hex[:6]}",
            target_type="event",
            target_id=evt2.event_id,
            assessment_type="uncertainty",
            rating="moderate",
            rationale="Acoustic harmonic matches latch strike; physical contact occurs near gate boundary.",
            assessed_by="Temporal Correlator Agent",
        )
        as3 = EvidenceAssessment(
            assessment_id=f"assess-{uuid.uuid4().hex[:6]}",
            target_type="event",
            target_id=evt3.event_id,
            assessment_type="support_level",
            rating="high",
            rationale="Cross-camera correlation established between cam-north-04 and cam-courtyard-02 with matching clothing and temporal continuity.",
            assessed_by="Temporal Correlation Agent",
        )
        self.repository.add_evidence_assessment(as1)
        self.repository.add_evidence_assessment(as2)
        self.repository.add_evidence_assessment(as3)

        # Coverage records for both camera feeds
        now = datetime.now(UTC)
        cov1 = CoverageRecord(
            coverage_id=f"cov-{uuid.uuid4().hex[:6]}",
            investigation_id=inv.investigation_id,
            source_reference_id=res1.media_asset.media_asset_id,
            status="examined",
            examined_at=now,
            notes="Complete timeline examination performed for North Perimeter Gate (cam-north-04).",
            artifact_ids=[a.artifact_id for a in res1.frame_artifacts + res1.audio_artifacts],
        )
        cov2 = CoverageRecord(
            coverage_id=f"cov-{uuid.uuid4().hex[:6]}",
            investigation_id=inv.investigation_id,
            source_reference_id=res2.media_asset.media_asset_id,
            status="examined",
            examined_at=now,
            notes="Complete timeline examination performed for Central Facility Courtyard (cam-courtyard-02).",
            artifact_ids=[a.artifact_id for a in res2.frame_artifacts + res2.audio_artifacts],
        )
        self.repository.add_coverage_record(cov1)
        self.repository.add_coverage_record(cov2)

        # Slice clips
        try:
            self.slice_incident_clip(inv.investigation_id, evt1.event_id, padding_seconds=0.5)
            self.slice_incident_clip(inv.investigation_id, evt4.event_id, padding_seconds=0.5)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Could not auto-slice demo clips: {exc}")

        all_obs = [obs1, obs2, obs3, obs4, obs5]
        all_evts = [evt1, evt2, evt3, evt4]

        rep = Report(
            report_id=f"rep-{uuid.uuid4().hex[:6]}",
            investigation_id=inv.investigation_id,
            title="Forensic Investigation Report: Multi-Camera Facility Intrusion Analysis",
            summary=(
                "Autonomous multi-camera forensic investigation confirms a coordinated premise breach across two synchronized feeds:\n\n"
                "### 1. Objective Finding & Direct Answer\n"
                "A single unauthorized intruder breached the North Gate at 00:01.20 (cam-north-04) and successfully traversed through the access corridor into the Central Facility Courtyard at 00:03.60 (cam-courtyard-02), advancing toward the building entrance by 00:05.80.\n\n"
                "### 2. Chronological Timeline Analysis (Cross-Camera Premise Correlation)\n"
                "- [00:01.20 - 00:03.50] Event: restricted_boundary_crossing (cam-north-04) — Suspect approaches and breaches yellow perimeter line.\n"
                "- [00:02.40 - 00:03.00] Event: security_hardware_tamper (cam-north-04) — Acoustic transient matches lock latch vibration.\n"
                "- [00:03.20 - 00:04.60] Event: cross_camera_premise_transition (cam-north-04 & cam-courtyard-02) — Cross-camera trajectory confirms suspect movement between feeds.\n"
                "- [00:04.00 - 00:05.80] Event: facility_courtyard_incursion (cam-courtyard-02) — Suspect advances across courtyard toward facility entrance.\n\n"
                "### 3. Evidence Integrity & Confidence\n"
                "Findings are corroborated across two independent camera views with continuous temporal alignment and high confidence (0.94-0.96)."
            ),
            observation_ids=[o.observation_id for o in all_obs],
            event_ids=[e.event_id for e in all_evts],
            assessment_ids=[as1.assessment_id, as2.assessment_id, as3.assessment_id],
            coverage_ids=[cov1.coverage_id, cov2.coverage_id],
            generated_by="Agentic Reporter & Synthesizer",
            version=1,
            status="draft",
        )
        self.repository.add_report(rep)

        st = InvestigationState(
            investigation_id=inv.investigation_id,
            status=InvestigationStatus.COMPLETED,
            completed_at=datetime.now(UTC),
            task_ids=["task-ingest-1", "task-ingest-2", "task-visual", "task-audio", "task-temporal", "task-verify", "task-report"],
            observation_ids=[o.observation_id for o in all_obs],
            event_ids=[e.event_id for e in all_evts],
        )
        self.repository.save_state(st)

        audit = AuditLog(
            audit_id=f"audit-{uuid.uuid4().hex[:8]}",
            investigation_id=inv.investigation_id,
            action="investigation_update",
            actor="Lead Det. Vance",
            target_type="investigation",
            target_id=inv.investigation_id,
            notes="Multi-camera premise demo case initialized with cross-camera correlation.",
        )
        self.repository.add_audit_log(audit)

        return inv, primary_result
