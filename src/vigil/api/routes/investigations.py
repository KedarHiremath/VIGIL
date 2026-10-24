"""FastAPI route handlers for investigation management and reporting."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from vigil.api.dependencies import get_investigation_service
from vigil.api.schemas import (
    EventEditRequest,
    EventReviewRequest,
    EventReviewResponse,
    IncidentClipSliceRequest,
    InvestigationCreateResponse,
    InvestigationStatusResponse,
    InvestigationSummaryResponse,
    MediaIngestResponse,
    ReportFinalizeRequest,
    ReportFinalizeResponse,
)
from vigil.domain.artifact import Artifact
from vigil.domain.audit import AuditLog
from vigil.domain.coverage import CoverageRecord
from vigil.domain.event import Event
from vigil.domain.evidence_assessment import EvidenceAssessment
from vigil.domain.investigation import Investigation
from vigil.domain.media_asset import MediaAsset
from vigil.domain.observation import Observation
from vigil.domain.report import Report
from vigil.orchestration.investigation_state import InvestigationStatus
from vigil.services.investigation_service import InvestigationService
from vigil.storage.repository import EntityNotFoundError

router = APIRouter(prefix="/api/v1/investigations", tags=["investigations"])


@router.post(
    "",
    response_model=InvestigationCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Upload video footage (single or multiple feeds) and initiate an investigation",
)
def create_investigation(
    file: Annotated[
        UploadFile | None,
        File(description="Single video footage file (.mp4, .mkv, .avi, etc.)"),
    ] = None,
    files: Annotated[
        list[UploadFile] | None,
        File(description="Multiple video footage files for multi-camera premise correlation"),
    ] = None,
    file_path: Annotated[
        str | None,
        Form(
            description="Path to an existing video file on the server if not uploading directly"
        ),
    ] = None,
    file_paths: Annotated[
        list[str] | str | None,
        Form(
            description="Paths to existing video files on the server (comma-separated or list)"
        ),
    ] = None,
    title: Annotated[
        str | None,
        Form(description="Investigation title"),
    ] = None,
    objective: Annotated[
        str | None,
        Form(description="Forensic objective and questions to verify"),
    ] = None,
    scope_description: Annotated[
        str | None,
        Form(description="Scope boundaries and camera details"),
    ] = None,
    camera_id: Annotated[
        str | None,
        Form(description="Unique camera ID (e.g. cam-north-01)"),
    ] = None,
    camera_ids: Annotated[
        str | None,
        Form(description="Comma-separated camera IDs for multiple feeds (e.g. cam-01,cam-02)"),
    ] = None,
    camera_name: Annotated[
        str | None,
        Form(description="Human readable camera name"),
    ] = None,
    camera_location: Annotated[
        str | None,
        Form(description="Camera location label"),
    ] = None,
    camera_timezone: Annotated[
        str | None,
        Form(description="Camera timezone (e.g. UTC, America/New_York)"),
    ] = None,
    sample_interval_seconds: Annotated[
        float,
        Form(
            description="Interval in seconds between extracted sample frames"
        ),
    ] = 2.0,
    max_frames: Annotated[
        int,
        Form(description="Maximum number of sample frames to extract per feed"),
    ] = 50,
    extract_audio: Annotated[
        bool,
        Form(description="Whether to demux and analyze audio track"),
    ] = True,
    run_async: Annotated[
        bool,
        Form(
            description="If True, processes investigation asynchronously in background"
        ),
    ] = True,
    created_by: Annotated[
        str | None,
        Form(description="Investigator username or badge ID"),
    ] = None,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> InvestigationCreateResponse:
    """Upload video footage (single or multiple feeds), perform physical media ingestion and frame/audio extraction,

    and initiate an autonomous agentic forensic investigation.
    """
    target_paths: list[Path] = []
    upload_dir = service.storage_dir / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # 1. Collect uploaded files sequentially
    all_uploads: list[UploadFile] = []
    if files:
        all_uploads.extend([f for f in files if f.filename])
    if file and file.filename:
        if not any(f.filename == file.filename for f in all_uploads):
            all_uploads.append(file)

    for up_file in all_uploads:
        unique_name = f"{uuid.uuid4().hex[:8]}_{up_file.filename}"
        t_path = upload_dir / unique_name
        try:
            with open(t_path, "wb") as buffer:
                shutil.copyfileobj(up_file.file, buffer)
            target_paths.append(t_path)
        finally:
            up_file.file.close()

    # 2. Collect existing server file paths
    if not target_paths:
        raw_paths: list[str] = []
        if isinstance(file_paths, list):
            raw_paths.extend(file_paths)
        elif isinstance(file_paths, str) and file_paths.strip():
            raw_paths.extend([p.strip() for p in file_paths.split(",") if p.strip()])
        if file_path and file_path.strip() and file_path not in raw_paths:
            raw_paths.append(file_path.strip())

        for p_str in raw_paths:
            p = Path(p_str).resolve()
            if not p.is_file():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Specified file_path does not exist: {p_str}",
                )
            target_paths.append(p)

    if not target_paths:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either a video file upload or a valid file_path is required.",
        )

    # Parse camera IDs if provided as comma-separated
    parsed_camera_ids: list[str] | None = None
    if camera_ids and camera_ids.strip():
        parsed_camera_ids = [c.strip() for c in camera_ids.split(",") if c.strip()]

    try:
        inv, result = service.create_and_ingest_investigation(
            file_paths=target_paths,
            title=title,
            objective=objective,
            scope_description=scope_description,
            camera_id=camera_id,
            camera_ids=parsed_camera_ids,
            camera_name=camera_name,
            camera_location=camera_location,
            camera_timezone=camera_timezone,
            sample_interval_seconds=sample_interval_seconds,
            max_frames=max_frames,
            extract_audio=extract_audio,
            created_by=created_by,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Media ingestion failed: {exc}",
        ) from exc

    # Start investigation
    service.run_investigation(inv.investigation_id, run_async=run_async)

    curr_status = service.get_status(inv.investigation_id)

    total_frames = sum(len(r.frame_artifacts) for r in result.all_ingestion_results)
    any_audio = any(len(r.audio_artifacts) > 0 for r in result.all_ingestion_results)
    all_cam_ids = [r.camera.camera_id for r in result.all_ingestion_results if r.camera]

    return InvestigationCreateResponse(
        investigation_id=inv.investigation_id,
        title=inv.title,
        status=curr_status.status.value,
        media_asset_id=result.media_asset.media_asset_id,
        media_asset_ids=inv.media_asset_ids,
        camera_id=result.camera.camera_id if result.camera else None,
        camera_ids=all_cam_ids,
        media_count=len(inv.media_asset_ids),
        frame_count=total_frames,
        has_audio=any_audio,
        message=(
            "Investigation initiated and running in background."
            if run_async
            else "Investigation completed."
        ),
    )


@router.post(
    "/{investigation_id}/media",
    response_model=MediaIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add and ingest additional surveillance video footage into an existing investigation",
)
def add_investigation_media(
    investigation_id: str,
    file: Annotated[
        UploadFile | None,
        File(description="Video footage file (.mp4, .mkv, .avi, etc.)"),
    ] = None,
    file_path: Annotated[
        str | None,
        Form(description="Path to an existing video file on the server"),
    ] = None,
    camera_id: Annotated[
        str | None,
        Form(description="Camera ID for this feed (e.g. cam-courtyard-02)"),
    ] = None,
    camera_name: Annotated[
        str | None,
        Form(description="Human readable camera name"),
    ] = None,
    camera_location: Annotated[
        str | None,
        Form(description="Camera location label"),
    ] = None,
    camera_timezone: Annotated[
        str | None,
        Form(description="Camera timezone (e.g. UTC)"),
    ] = None,
    sample_interval_seconds: Annotated[
        float,
        Form(description="Interval in seconds between sample frames"),
    ] = 2.0,
    max_frames: Annotated[
        int,
        Form(description="Maximum sample frames to extract"),
    ] = 50,
    extract_audio: Annotated[
        bool,
        Form(description="Whether to demux audio track"),
    ] = True,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> MediaIngestResponse:
    """Add another camera feed / video file to an existing investigation."""
    try:
        service.get_investigation(investigation_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation '{investigation_id}' not found.",
        ) from exc

    target_path: Path
    if file is not None and file.filename:
        upload_dir = service.storage_dir / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        unique_name = f"{uuid.uuid4().hex[:8]}_{file.filename}"
        target_path = upload_dir / unique_name
        try:
            with open(target_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
        finally:
            file.file.close()
    elif file_path:
        target_path = Path(file_path).resolve()
        if not target_path.is_file():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Specified file_path does not exist: {file_path}",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either a video file upload or a valid file_path is required.",
        )

    try:
        result = service.add_and_ingest_media(
            investigation_id=investigation_id,
            file_path=target_path,
            camera_id=camera_id,
            camera_name=camera_name,
            camera_location=camera_location,
            camera_timezone=camera_timezone,
            sample_interval_seconds=sample_interval_seconds,
            max_frames=max_frames,
            extract_audio=extract_audio,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Media ingestion failed: {exc}",
        ) from exc

    return MediaIngestResponse(
        investigation_id=investigation_id,
        media_asset_id=result.media_asset.media_asset_id,
        camera_id=result.camera.camera_id if result.camera else None,
        frame_count=len(result.frame_artifacts),
        has_audio=len(result.audio_artifacts) > 0,
        message=f"Surveillance feed successfully added and ingested as '{result.media_asset.media_asset_id}'.",
    )


@router.get(
    "/{investigation_id}/status",
    response_model=InvestigationStatusResponse,
    summary="Poll task progress and lifecycle state",
)
def get_investigation_status(
    investigation_id: str,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> InvestigationStatusResponse:
    """Poll the real-time status, completed tasks, observation counts,

    event counts, and report readiness for an investigation.
    """
    try:
        status_info = service.get_status(investigation_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation '{investigation_id}' not found.",
        ) from exc

    return InvestigationStatusResponse(
        investigation_id=status_info.investigation_id,
        status=status_info.status.value,
        created_at=status_info.created_at,
        updated_at=status_info.updated_at,
        started_at=status_info.started_at,
        completed_at=status_info.completed_at,
        completed_tasks=status_info.completed_tasks,
        task_ids=status_info.task_ids,
        observation_count=status_info.observation_count,
        event_count=status_info.event_count,
        coverage_count=status_info.coverage_count,
        has_report=status_info.has_report,
        report_id=status_info.report_id,
        error=status_info.error,
    )


@router.get(
    "/{investigation_id}/report",
    response_model=Report,
    summary="Retrieve the compiled forensic report",
)
def get_investigation_report(
    investigation_id: str,
    format: Annotated[
        str | None,
        Query(
            description="Set to 'markdown' or 'text' for formatted text"
        ),
    ] = None,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> Response | Report:
    """Retrieve the compiled forensic report with observations, events,

    evidence assessments, and coverage links.
    """
    try:
        status_info = service.get_status(investigation_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation '{investigation_id}' not found.",
        ) from exc

    if status_info.status in {
        InvestigationStatus.CREATED,
        InvestigationStatus.RUNNING,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Investigation '{investigation_id}' is still in status "
                f"'{status_info.status.value}'. Report has not yet been generated."
            ),
        )

    report = service.get_report(investigation_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No forensic report generated for investigation '{investigation_id}'.",
        )

    if format in {"markdown", "md", "text"}:
        md_text = service.export_report_markdown(investigation_id, report.report_id)
        return Response(content=md_text, media_type="text/markdown")

    if format == "html":
        html_content = service.export_report_html(investigation_id, report.report_id)
        return Response(content=html_content, media_type="text/html")

    if format == "pdf":
        pdf_bytes = service.export_report_pdf(investigation_id, report.report_id)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="report_{investigation_id}.pdf"'},
        )

    return report


@router.get(
    "",
    response_model=list[InvestigationSummaryResponse],
    summary="List all investigations",
)
def list_investigations(
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> list[InvestigationSummaryResponse]:
    """List all registered forensic investigations."""
    investigations = service.list_investigations()
    summaries: list[InvestigationSummaryResponse] = []
    for inv in investigations:
        try:
            st = service.get_status(inv.investigation_id)
            status_val = st.status.value
        except Exception:  # noqa: BLE001
            status_val = "created"

        summaries.append(
            InvestigationSummaryResponse(
                investigation_id=inv.investigation_id,
                title=inv.title,
                objective=inv.objective,
                status=status_val,
                created_at=inv.created_at,
                media_asset_ids=inv.media_asset_ids,
            )
        )
    return summaries


@router.get(
    "/{investigation_id}",
    response_model=Investigation,
    summary="Get full investigation domain record",
)
def get_investigation_details(
    investigation_id: str,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> Investigation:
    """Fetch complete Investigation domain record."""
    try:
        return service.get_investigation(investigation_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation '{investigation_id}' not found.",
        ) from exc


@router.get(
    "/{investigation_id}/observations",
    response_model=list[Observation],
    summary="Get observations identified during investigation",
)
def get_investigation_observations(
    investigation_id: str,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> list[Observation]:
    """Retrieve all observations associated with an investigation."""
    try:
        service.get_investigation(investigation_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation '{investigation_id}' not found.",
        ) from exc

    return service.get_observations(investigation_id)


@router.get(
    "/{investigation_id}/events",
    response_model=list[Event],
    summary="Get events correlated during investigation",
)
def get_investigation_events(
    investigation_id: str,
    event_status: Annotated[
        str | None,
        Query(
            alias="status",
            description="Filter events by review status: proposed, under_review, confirmed, rejected",
        ),
    ] = None,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> list[Event]:
    """Retrieve correlated events associated with an investigation, optionally filtered by status."""
    try:
        service.get_investigation(investigation_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation '{investigation_id}' not found.",
        ) from exc

    events = service.get_events(investigation_id)
    if event_status:
        events = [e for e in events if e.status.lower() == event_status.lower()]
    return events


@router.get(
    "/{investigation_id}/coverage",
    response_model=list[CoverageRecord],
    summary="Get coverage records for an investigation",
)
def get_investigation_coverage(
    investigation_id: str,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> list[CoverageRecord]:
    """Retrieve coverage records for an investigation."""
    try:
        service.get_investigation(investigation_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation '{investigation_id}' not found.",
        ) from exc

    return service.get_coverage_records(investigation_id)


@router.get(
    "/{investigation_id}/artifacts",
    response_model=list[Artifact],
    summary="Get extracted artifacts (frames, audio, clips) for an investigation",
)
def get_investigation_artifacts(
    investigation_id: str,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> list[Artifact]:
    """Retrieve extracted frames, audio tracks, and clip artifacts."""
    try:
        service.get_investigation(investigation_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation '{investigation_id}' not found.",
        ) from exc

    return service.get_artifacts(investigation_id)


@router.get(
    "/{investigation_id}/events/{event_id}",
    response_model=Event,
    summary="Get single event details",
)
def get_investigation_event_details(
    investigation_id: str,
    event_id: str,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> Event:
    """Retrieve specific event record by ID."""
    try:
        service.get_investigation(investigation_id)
        return service.repository.get_event(event_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{investigation_id}/events/{event_id}/review",
    response_model=EventReviewResponse,
    summary="Human investigator review decision on a proposed event",
)
def review_event(
    investigation_id: str,
    event_id: str,
    payload: EventReviewRequest,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> EventReviewResponse:
    """Submit human verification (confirm or reject) or update review status for an event."""
    try:
        updated_event, audit_log = service.review_event(
            investigation_id=investigation_id,
            event_id=event_id,
            status=payload.status,
            reviewer=payload.reviewer,
            notes=payload.notes,
            description=payload.description,
            event_type=payload.event_type,
            start_seconds=payload.start_seconds,
            end_seconds=payload.end_seconds,
            start_time=payload.start_time,
            end_time=payload.end_time,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    return EventReviewResponse(
        event=updated_event,
        audit_log=audit_log,
        message=f"Event '{event_id}' review status updated to '{payload.status}'.",
    )


@router.patch(
    "/{investigation_id}/events/{event_id}",
    response_model=EventReviewResponse,
    summary="Directly edit event attributes with audit logging",
)
def edit_event(
    investigation_id: str,
    event_id: str,
    payload: EventEditRequest,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> EventReviewResponse:
    """Apply direct investigator edits to an event record."""
    updates = payload.model_dump(exclude_unset=True, exclude={"editor", "notes"})
    try:
        updated_event, audit_log = service.edit_event(
            investigation_id=investigation_id,
            event_id=event_id,
            editor=payload.editor,
            updates=updates,
            notes=payload.notes,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    return EventReviewResponse(
        event=updated_event,
        audit_log=audit_log,
        message=f"Event '{event_id}' updated successfully.",
    )


@router.post(
    "/{investigation_id}/events/{event_id}/clip",
    response_model=Artifact,
    summary="Cut playable incident video sub-clip for event",
)
def slice_event_clip(
    investigation_id: str,
    event_id: str,
    payload: IncidentClipSliceRequest | None = None,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> Artifact:
    """Extract playable incident video sub-clip around event interval."""
    padding = payload.padding_seconds if payload else 1.0
    try:
        return service.slice_incident_clip(
            investigation_id=investigation_id,
            event_id=event_id,
            padding_seconds=padding,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Clip extraction failed: {exc}",
        ) from exc


@router.get(
    "/{investigation_id}/audit",
    response_model=list[AuditLog],
    summary="Query audit trail of review decisions and modifications",
)
def get_investigation_audit_logs(
    investigation_id: str,
    target_id: Annotated[str | None, Query(description="Filter by target record ID")] = None,
    actor: Annotated[str | None, Query(description="Filter by investigator/actor")] = None,
    action: Annotated[str | None, Query(description="Filter by action type")] = None,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> list[AuditLog]:
    """Retrieve chronological audit trail of human review actions and system updates."""
    try:
        return service.get_audit_logs(
            investigation_id=investigation_id,
            target_id=target_id,
            actor=actor,
            action=action,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.post(
    "/{investigation_id}/report/finalize",
    response_model=ReportFinalizeResponse,
    summary="Finalize forensic report with incident clips and review conclusions",
)
def finalize_investigation_report(
    investigation_id: str,
    payload: ReportFinalizeRequest,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> ReportFinalizeResponse:
    """Finalize the investigation report, incorporating verified event decisions and incident clips."""
    try:
        final_report, audit_log = service.finalize_report(
            investigation_id=investigation_id,
            finalized_by=payload.finalized_by,
            title=payload.title,
            summary=payload.summary,
            notes=payload.notes,
            auto_slice_clips=payload.auto_slice_clips,
        )
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Report finalization failed: {exc}",
        ) from exc

    return ReportFinalizeResponse(
        report=final_report,
        audit_log=audit_log,
        version=final_report.version,
        clip_count=len(final_report.clip_artifact_ids),
        message=f"Report finalized as version {final_report.version} by {payload.finalized_by}.",
    )


@router.get(
    "/{investigation_id}/export/html",
    summary="Export finalized forensic report as interactive standalone HTML",
)
def export_report_html(
    investigation_id: str,
    request: Request,
    report_id: Annotated[str | None, Query(description="Optional specific report ID")] = None,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> Response:
    """Generate interactive HTML forensic report with embedded incident video clips."""
    base_url = str(request.base_url).rstrip("/")
    try:
        html_doc = service.export_report_html(
            investigation_id=investigation_id,
            report_id=report_id,
            base_url=base_url,
        )
        return Response(content=html_doc, media_type="text/html")
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/{investigation_id}/export/pdf",
    summary="Export finalized forensic report as publication-grade PDF deliverable",
)
def export_report_pdf(
    investigation_id: str,
    report_id: Annotated[str | None, Query(description="Optional specific report ID")] = None,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> Response:
    """Generate court/audit-ready PDF document with metadata, event tables, and audit trail."""
    try:
        pdf_bytes = service.export_report_pdf(
            investigation_id=investigation_id,
            report_id=report_id,
        )
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="report_{investigation_id}.pdf"'
            },
        )
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/{investigation_id}/artifacts/{artifact_id}/content",
    summary="Stream or download extracted media artifact file (video clip, frame image, audio)",
)
def get_artifact_content(
    investigation_id: str,
    artifact_id: str,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> FileResponse:
    """Stream or download actual artifact file content for browser playback or viewing."""
    try:
        service.get_investigation(investigation_id)
        artifact = service.repository.get_artifact(artifact_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    local_path = service.get_artifact_content_path(artifact_id)
    if not local_path or not local_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Artifact media file for '{artifact_id}' not found on server storage.",
        )

    media_type = "video/mp4" if artifact.media_type == "video" else ("audio/wav" if artifact.media_type == "audio" else "image/jpeg")
    # Use content_disposition_type="inline" so browsers stream/play the file
    # instead of downloading it. Passing filename= with the default "attachment"
    # disposition causes browsers to abort the TCP connection after receiving a
    # 206 Partial Content response, producing [WinError 10054] noise in the logs.
    return FileResponse(
        path=local_path,
        media_type=media_type,
        filename=local_path.name,
        content_disposition_type="inline",
    )


@router.post(
    "/demo",
    response_model=InvestigationCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Seed and initialize a rich multi-camera demo forensic investigation",
)
def create_demo_investigation(
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> InvestigationCreateResponse:
    """Initialize a rich sample multi-modal investigation with synthetic surveillance video,

    extracted frames, acoustic cues, observations, events, and reports.
    """
    try:
        inv, result = service.create_demo_investigation()
        total_frames = sum(len(r.frame_artifacts) for r in result.all_ingestion_results)
        any_audio = any(len(r.audio_artifacts) > 0 for r in result.all_ingestion_results)
        all_cam_ids = [r.camera.camera_id for r in result.all_ingestion_results if r.camera]
        return InvestigationCreateResponse(
            investigation_id=inv.investigation_id,
            title=inv.title,
            status="completed",
            media_asset_id=result.media_asset.media_asset_id,
            media_asset_ids=inv.media_asset_ids,
            camera_id=result.camera.camera_id if result.camera else None,
            camera_ids=all_cam_ids,
            media_count=len(inv.media_asset_ids),
            frame_count=total_frames,
            has_audio=any_audio,
            message="Multi-camera demo forensic investigation seeded successfully.",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to create demo investigation: {exc}",
        ) from exc


@router.get(
    "/{investigation_id}/media",
    response_model=list[MediaAsset],
    summary="Get media assets associated with an investigation",
)
def get_investigation_media_assets(
    investigation_id: str,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> list[MediaAsset]:
    """Retrieve all physical media assets registered under this case."""
    try:
        return service.get_media_assets(investigation_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/{investigation_id}/media/primary/content",
    summary="Stream primary video footage of the investigation",
)
def get_primary_media_content(
    investigation_id: str,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> FileResponse:
    """Convenience endpoint to stream the primary ingested video file for in-browser playback."""
    try:
        inv = service.get_investigation(investigation_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    if not inv.media_asset_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No media assets associated with this investigation.",
        )

    primary_id = inv.media_asset_ids[0]
    return get_media_asset_content(investigation_id, primary_id, service)


@router.get(
    "/{investigation_id}/media/{media_asset_id}/content",
    summary="Stream primary footage or media asset content",
)
def get_media_asset_content(
    investigation_id: str,
    media_asset_id: str,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> FileResponse:
    """Stream original video footage or audio asset file."""
    try:
        service.get_investigation(investigation_id)
        asset = service.repository.get_media_asset(media_asset_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    local_path = service.get_media_asset_content_path(media_asset_id)
    if not local_path or not local_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Media file for asset '{media_asset_id}' not found on server storage.",
        )

    media_type = "video/mp4" if asset.media_type == "video" else ("audio/wav" if asset.media_type == "audio" else "image/jpeg")
    # Use content_disposition_type="inline" so browsers stream/play the file
    # instead of downloading it. Passing filename= with the default "attachment"
    # disposition causes browsers to abort the TCP connection after receiving a
    # 206 Partial Content response, producing [WinError 10054] noise in the logs.
    return FileResponse(
        path=local_path,
        media_type=media_type,
        filename=local_path.name,
        content_disposition_type="inline",
    )


@router.get(
    "/{investigation_id}/assessments",
    response_model=list[EvidenceAssessment],
    summary="Get evidence quality and support assessments",
)
def get_investigation_assessments(
    investigation_id: str,
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> list[EvidenceAssessment]:
    """Retrieve evidence assessments for an investigation."""
    try:
        return service.get_evidence_assessments(investigation_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
