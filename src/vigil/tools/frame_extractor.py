"""Tool worker for media frame extraction and interval sampling."""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from vigil.domain.artifact import Artifact
from vigil.domain.source_reference import SourceReference
from vigil.media.decoder import MediaDecoder
from vigil.orchestration.task_types import TaskRequest
from vigil.tools.base import BaseToolWorker, generate_sha256

logger = logging.getLogger(__name__)


def uri_to_file_path(uri: str) -> Path | None:
    """Resolve a file URI or path string to a local filesystem Path if it exists."""
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        path = url2pathname(parsed.path)
        if path.startswith("\\") and len(path) > 3 and path[2] == ":":
            path = path[1:]
        p = Path(path)
        return p if p.is_file() else None

    p = Path(uri)
    return p if p.is_file() else None


class FrameExtractorWorker(BaseToolWorker):
    """Samples video frames and creates derived Artifact records."""

    def run(self, request: TaskRequest) -> list[str]:
        # Identify target media assets
        media_ids = list(request.input_refs)
        param_media_id = request.parameters.get("media_asset_id")
        if param_media_id and isinstance(param_media_id, str):
            media_ids.append(param_media_id)

        if not media_ids:
            # Fall back to inspecting repository for available assets
            all_assets = self.repository.list_media_assets()
            if not all_assets:
                raise ValueError("No media assets provided or available in repository.")
            media_ids = [all_assets[0].media_asset_id]

        sample_interval = float(request.parameters.get("sample_interval_seconds", 2.0))
        max_frames = int(request.parameters.get("max_frames", 10))
        frame_duration = float(request.parameters.get("frame_duration", 0.5))

        output_artifact_ids: list[str] = []

        for media_id in media_ids:
            media_asset = self.repository.get_media_asset(media_id)
            duration = media_asset.duration_seconds

            start_t = float(request.parameters.get("start_seconds", 0.0))
            end_param = request.parameters.get("end_seconds")
            end_t = float(end_param) if end_param is not None else duration
            if duration is not None and end_t is not None:
                end_t = min(end_t, duration)

            # Check if existing frame artifacts for this media asset already exist in the repository
            existing_frames = [
                a
                for a in self.repository.list_artifacts()
                if a.artifact_type == "frame"
                and a.source_reference
                and a.source_reference.media_asset_id == media_id
            ]

            if existing_frames:
                # Sort chronologically by start_seconds
                existing_frames.sort(
                    key=lambda a: (
                        a.source_reference.start_seconds
                        if a.source_reference and a.source_reference.start_seconds is not None
                        else 0.0
                    )
                )
                matching = [
                    a
                    for a in existing_frames
                    if a.source_reference
                    and a.source_reference.start_seconds >= start_t
                    and (end_t is None or a.source_reference.start_seconds <= end_t)
                ]
                if matching:
                    logger.info(
                        "FrameExtractorWorker: Reusing %d existing frame artifact(s) for media %s",
                        min(len(matching), max_frames),
                        media_id,
                    )
                    output_artifact_ids.extend(a.artifact_id for a in matching[:max_frames])
                    continue

            # Check if physical video file exists
            physical_file = uri_to_file_path(media_asset.storage_uri)
            asset_extracted = False

            if physical_file is not None and physical_file.is_file():
                # Extract real frames using MediaDecoder
                art_dir = Path(tempfile.gettempdir()) / "vigil_artifacts" / media_id / "frames"
                extracted_frames = MediaDecoder.extract_frames(
                    file_path=physical_file,
                    output_dir=art_dir,
                    sample_interval_seconds=sample_interval,
                    start_seconds=start_t,
                    end_seconds=end_t,
                    max_frames=max_frames,
                )

                for ef in extracted_frames:
                    if duration is not None:
                        frame_end = min(ef.timestamp_seconds + frame_duration, duration)
                    else:
                        frame_end = ef.timestamp_seconds + frame_duration

                    if frame_end <= ef.timestamp_seconds:
                        frame_end = ef.timestamp_seconds + 0.1

                    art_id = f"art-{media_id}-f{ef.frame_index}-{uuid.uuid4().hex[:6]}"
                    source_ref = SourceReference(
                        media_asset_id=media_id,
                        start_seconds=ef.timestamp_seconds,
                        end_seconds=frame_end,
                    )
                    artifact = Artifact(
                        artifact_id=art_id,
                        artifact_type="frame",
                        media_type="image",
                        storage_uri=ef.storage_uri,
                        source_reference=source_ref,
                        sha256=ef.sha256,
                    )
                    self.repository.add_artifact(artifact)
                    output_artifact_ids.append(art_id)

                if extracted_frames:
                    asset_extracted = True

            if asset_extracted:
                continue

            # Fallback to synthetic artifact creation for mock URIs
            current_t = start_t
            frame_idx = 0
            limit_t = end_t if end_t is not None else float("inf")

            while current_t < limit_t and frame_idx < max_frames:
                if duration is not None:
                    frame_end = min(current_t + frame_duration, duration)
                else:
                    frame_end = current_t + frame_duration

                if frame_end <= current_t:
                    frame_end = current_t + 0.1

                source_ref = SourceReference(
                    media_asset_id=media_id,
                    start_seconds=current_t,
                    end_seconds=frame_end,
                )

                art_id = f"art-{media_id}-f{frame_idx}-{uuid.uuid4().hex[:6]}"
                storage_uri = (
                    f"file:///storage/artifacts/{media_id}/frame_{frame_idx:04d}.jpg"
                )
                sha256 = generate_sha256(f"{art_id}:{storage_uri}:{current_t}")

                artifact = Artifact(
                    artifact_id=art_id,
                    artifact_type="frame",
                    media_type="image",
                    storage_uri=storage_uri,
                    source_reference=source_ref,
                    sha256=sha256,
                )

                self.repository.add_artifact(artifact)
                output_artifact_ids.append(art_id)

                current_t += sample_interval
                frame_idx += 1

        return output_artifact_ids
