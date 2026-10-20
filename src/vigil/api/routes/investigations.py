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
    Response,
    UploadFile,
    status,
)

from vigil.api.dependencies import get_investigation_service
from vigil.api.schemas import (
    InvestigationCreateResponse,
    InvestigationStatusResponse,
    InvestigationSummaryResponse,
)
from vigil.domain.artifact import Artifact
from vigil.domain.coverage import CoverageRecord
from vigil.domain.event import Event
from vigil.domain.investigation import Investigation
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
    summary="Upload video footage and initiate an investigation",
)
def create_investigation(
    file: Annotated[
        UploadFile | None,
        File(description="Video footage file (.mp4, .mkv, .avi, etc.)"),
    ] = None,
    file_path: Annotated[
        str | None,
        Form(
            description="Path to an existing video file on the server if not uploading directly"
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
        Form(description="Maximum number of sample frames to extract"),
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
    """Upload video footage, perform physical media ingestion and frame/audio extraction,

    and initiate an autonomous agentic forensic investigation.
    """
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
        inv, result = service.create_and_ingest_investigation(
            file_path=target_path,
            title=title,
            objective=objective,
            scope_description=scope_description,
            camera_id=camera_id,
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

    return InvestigationCreateResponse(
        investigation_id=inv.investigation_id,
        title=inv.title,
        status=curr_status.status.value,
        media_asset_id=result.media_asset.media_asset_id,
        camera_id=result.camera.camera_id if result.camera else None,
        frame_count=len(result.frame_artifacts),
        has_audio=len(result.audio_artifacts) > 0,
        message=(
            "Investigation initiated and running in background."
            if run_async
            else "Investigation completed."
        ),
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
        md_text = (
            f"# {report.title}\n\n"
            f"**Investigation ID**: {report.investigation_id}  \n"
            f"**Report ID**: {report.report_id}  \n"
            f"**Generated By**: {report.generated_by}  \n"
            f"**Generated At**: {report.generated_at.isoformat()}  \n\n"
            f"## Executive Summary\n\n"
            f"{report.summary}\n\n"
            f"## Findings Summary\n\n"
            f"- **Observations**: {len(report.observation_ids)}\n"
            f"- **Correlated Events**: {len(report.event_ids)}\n"
            f"- **Evidence Assessments**: {len(report.assessment_ids)}\n"
            f"- **Coverage Records**: {len(report.coverage_ids)}\n"
        )
        return Response(content=md_text, media_type="text/markdown")

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
    service: Annotated[
        InvestigationService,
        Depends(get_investigation_service),
    ] = None,  # type: ignore[assignment]
) -> list[Event]:
    """Retrieve all correlated events associated with an investigation."""
    try:
        service.get_investigation(investigation_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Investigation '{investigation_id}' not found.",
        ) from exc

    return service.get_events(investigation_id)


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
