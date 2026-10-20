"""Worker tool for ingesting physical media files into VIGIL."""

from __future__ import annotations

from pathlib import Path

from vigil.media.ingestion import MediaIngestionService
from vigil.orchestration.task_types import TaskRequest
from vigil.tools.base import BaseToolWorker


class MediaIngestionWorker(BaseToolWorker):
    """Forensic tool worker for physical media ingestion and artifact indexing."""

    def run(self, request: TaskRequest) -> list[str]:
        # Identify source file path
        file_path_param = request.parameters.get("file_path")
        file_path: str | None = None
        if file_path_param and isinstance(file_path_param, str):
            file_path = file_path_param
        elif request.input_refs:
            file_path = request.input_refs[0]

        if not file_path:
            raise ValueError("No file_path provided in task parameters or input_refs.")

        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Source media file not found: {file_path}")

        camera_id = request.parameters.get("camera_id")
        camera_name = request.parameters.get("camera_name")
        camera_loc = request.parameters.get("camera_location")
        camera_tz = request.parameters.get("camera_timezone")

        sample_interval = float(request.parameters.get("sample_interval_seconds", 2.0))
        max_frames = int(request.parameters.get("max_frames", 50))
        extract_audio = bool(request.parameters.get("extract_audio", True))
        output_dir = request.parameters.get("output_dir")

        service = MediaIngestionService(repository=self.repository)
        result = service.ingest_file(
            file_path=path,
            camera_id=str(camera_id) if camera_id else None,
            camera_name=str(camera_name) if camera_name else None,
            camera_location=str(camera_loc) if camera_loc else None,
            camera_timezone=str(camera_tz) if camera_tz else None,
            output_artifacts_dir=str(output_dir) if output_dir else None,
            sample_interval_seconds=sample_interval,
            max_frames=max_frames,
            extract_audio=extract_audio,
        )

        return [result.media_asset.media_asset_id, *result.all_artifact_ids]
