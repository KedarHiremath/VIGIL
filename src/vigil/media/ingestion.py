"""Media ingestion and indexing service connecting physical files to VIGIL repository."""

from __future__ import annotations

import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from vigil.domain.artifact import Artifact
from vigil.domain.camera import Camera
from vigil.domain.media_asset import MediaAsset
from vigil.domain.source_reference import SourceReference
from vigil.media.decoder import MediaDecoder
from vigil.media.metadata import MediaMetadata, MediaMetadataExtractor
from vigil.storage.repository import InvestigationRepository


@dataclass(frozen=True)
class IngestionResult:
    """Outcome of ingesting and indexing a physical media asset."""

    media_asset: MediaAsset
    camera: Camera | None
    frame_artifacts: list[Artifact]
    audio_artifacts: list[Artifact]

    @property
    def all_artifact_ids(self) -> list[str]:
        return [a.artifact_id for a in self.frame_artifacts + self.audio_artifacts]


class MediaIngestionService:
    """Service that validates media, extracts metadata, extracts frames & audio, and registers assets in repository."""

    def __init__(self, repository: InvestigationRepository) -> None:
        self.repository = repository

    def ingest_file(
        self,
        file_path: str | Path,
        media_asset_id: str | None = None,
        camera_id: str | None = None,
        camera_name: str | None = None,
        camera_location: str | None = None,
        camera_timezone: str | None = None,
        recorded_at: datetime | None = None,
        output_artifacts_dir: str | Path | None = None,
        sample_interval_seconds: float = 2.0,
        max_frames: int = 50,
        extract_audio: bool = True,
    ) -> IngestionResult:
        """Ingest a physical media file, populate MediaAsset and Camera, extract JPEG frames & WAV audio, and store in repository."""
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Media file does not exist: {path}")

        # 1. Metadata extraction
        metadata: MediaMetadata = MediaMetadataExtractor.extract(path)

        # 2. Camera setup if camera info provided
        created_camera: Camera | None = None
        if camera_id is not None:
            try:
                created_camera = self.repository.get_camera(camera_id)
            except Exception:  # noqa: BLE001
                created_camera = Camera(
                    camera_id=camera_id,
                    name=camera_name or f"Camera {camera_id}",
                    location_label=camera_location,
                    timezone=camera_timezone,
                )
                self.repository.add_camera(created_camera)

        # 3. Create MediaAsset
        asset_id = media_asset_id or f"media-{uuid.uuid4().hex[:8]}"
        media_asset = MediaMetadataExtractor.to_media_asset(
            metadata=metadata,
            media_asset_id=asset_id,
            camera_id=camera_id,
            storage_uri=path.as_uri(),
            recorded_at=recorded_at,
        )
        self.repository.add_media_asset(media_asset)

        # 4. Storage directory for extracted artifacts
        if output_artifacts_dir is not None:
            art_dir = Path(output_artifacts_dir).resolve() / asset_id
        else:
            art_dir = Path(tempfile.gettempdir()) / "vigil_artifacts" / asset_id
        art_dir.mkdir(parents=True, exist_ok=True)

        frame_artifacts: list[Artifact] = []
        audio_artifacts: list[Artifact] = []

        # 5. Extract JPEG frames for visual detection
        if metadata.has_video:
            extracted_frames = MediaDecoder.extract_frames(
                file_path=path,
                output_dir=art_dir / "frames",
                sample_interval_seconds=sample_interval_seconds,
                start_seconds=0.0,
                end_seconds=metadata.duration_seconds if metadata.duration_seconds > 0 else None,
                max_frames=max_frames,
            )

            duration = metadata.duration_seconds or 10.0
            for ef in extracted_frames:
                frame_end = min(ef.timestamp_seconds + sample_interval_seconds, duration)
                if frame_end <= ef.timestamp_seconds:
                    frame_end = ef.timestamp_seconds + 0.1

                art_id = f"art-{asset_id}-frame-{ef.frame_index:04d}-{uuid.uuid4().hex[:4]}"
                source_ref = SourceReference(
                    media_asset_id=asset_id,
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
                frame_artifacts.append(artifact)

        # 6. Demux audio track to .wav for acoustic transcription
        if metadata.has_audio and extract_audio:
            wav_out_path = art_dir / "audio" / "audio_track.wav"
            try:
                demuxed = MediaDecoder.demux_audio_to_wav(
                    file_path=path,
                    output_path=wav_out_path,
                    start_seconds=0.0,
                    end_seconds=metadata.duration_seconds if metadata.duration_seconds > 0 else None,
                )
                art_id = f"art-{asset_id}-audio-{uuid.uuid4().hex[:6]}"
                source_ref = SourceReference(
                    media_asset_id=asset_id,
                    start_seconds=0.0,
                    end_seconds=demuxed.duration_seconds if demuxed.duration_seconds > 0 else 0.1,
                )
                audio_artifact = Artifact(
                    artifact_id=art_id,
                    artifact_type="audio_segment",
                    media_type="audio",
                    storage_uri=demuxed.storage_uri,
                    source_reference=source_ref,
                    sha256=demuxed.sha256,
                )
                self.repository.add_artifact(audio_artifact)
                audio_artifacts.append(audio_artifact)
            except Exception:  # noqa: BLE001, S110
                # If audio demuxing fails on non-standard stream, proceed with frames
                pass

        return IngestionResult(
            media_asset=media_asset,
            camera=created_camera,
            frame_artifacts=frame_artifacts,
            audio_artifacts=audio_artifacts,
        )
