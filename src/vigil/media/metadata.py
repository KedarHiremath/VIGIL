"""Media metadata extraction and domain model populator for VIGIL."""

from __future__ import annotations

import hashlib
import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import av
import cv2

from vigil.domain.camera import Camera
from vigil.domain.media_asset import MediaAsset


@dataclass(frozen=True)
class MediaMetadata:
    """Rich container metadata extracted from a physical media file."""

    file_path: str
    storage_uri: str
    sha256: str
    duration_seconds: float
    media_type: Literal["video", "audio", "image"]
    file_size_bytes: int
    format_name: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    video_codec: str | None = None
    frame_count: int | None = None
    audio_sample_rate: int | None = None
    audio_channels: int | None = None
    audio_codec: str | None = None
    has_video: bool = False
    has_audio: bool = False


class MediaMetadataExtractor:
    """Extracts physical media attributes using PyAV and OpenCV."""

    @staticmethod
    def compute_sha256(file_path: str | Path) -> str:
        """Compute the SHA-256 checksum of a file without loading it entirely into RAM."""
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"Media file not found: {path}")

        hasher = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @classmethod
    def extract(cls, file_path: str | Path) -> MediaMetadata:
        """Probe a media file and return structured MediaMetadata."""
        path = Path(file_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Media file not found: {path}")

        file_size = path.stat().st_size
        sha256_sum = cls.compute_sha256(path)
        file_uri = path.as_uri()

        # Attempt extraction via PyAV first
        try:
            with av.open(str(path)) as container:
                format_name = container.format.name if container.format else None
                container_duration: float | None = None
                if container.duration is not None and container.duration > 0:
                    container_duration = float(container.duration) / float(av.time_base)

                has_video = len(container.streams.video) > 0
                has_audio = len(container.streams.audio) > 0

                width: int | None = None
                height: int | None = None
                fps: float | None = None
                video_codec: str | None = None
                frame_count: int | None = None
                video_duration: float | None = None

                if has_video:
                    v_stream = container.streams.video[0]
                    width = v_stream.width
                    height = v_stream.height
                    video_codec = v_stream.codec_context.name if v_stream.codec_context else None
                    if v_stream.average_rate is not None and float(v_stream.average_rate) > 0:
                        fps = float(v_stream.average_rate)
                    elif v_stream.rate is not None and float(v_stream.rate) > 0:
                        fps = float(v_stream.rate)

                    frame_count = v_stream.frames if v_stream.frames > 0 else None
                    if v_stream.duration is not None and v_stream.time_base is not None:
                        video_duration = float(v_stream.duration * v_stream.time_base)

                audio_sample_rate: int | None = None
                audio_channels: int | None = None
                audio_codec: str | None = None
                audio_duration: float | None = None

                if has_audio:
                    a_stream = container.streams.audio[0]
                    audio_sample_rate = a_stream.rate
                    audio_channels = a_stream.channels
                    audio_codec = a_stream.codec_context.name if a_stream.codec_context else None
                    if a_stream.duration is not None and a_stream.time_base is not None:
                        audio_duration = float(a_stream.duration * a_stream.time_base)

                # Determine effective duration
                duration = container_duration or video_duration or audio_duration
                if (duration is None or duration <= 0) and has_video and fps and frame_count:
                    duration = float(frame_count) / fps
                if duration is None or duration <= 0:
                    duration = 0.0

                # Determine media type
                if has_video:
                    media_type: Literal["video", "audio", "image"] = "video"
                elif has_audio:
                    media_type = "audio"
                elif path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}:
                    media_type = "image"
                else:
                    media_type = "video"

                return MediaMetadata(
                    file_path=str(path),
                    storage_uri=file_uri,
                    sha256=sha256_sum,
                    duration_seconds=round(duration, 3) if duration else 0.0,
                    media_type=media_type,
                    file_size_bytes=file_size,
                    format_name=format_name,
                    width=width,
                    height=height,
                    fps=round(fps, 3) if fps else None,
                    video_codec=video_codec,
                    frame_count=frame_count,
                    audio_sample_rate=audio_sample_rate,
                    audio_channels=audio_channels,
                    audio_codec=audio_codec,
                    has_video=has_video,
                    has_audio=has_audio,
                )
        except Exception:  # noqa: BLE001, S110
            # Fallback to OpenCV probing for images/videos
            pass

        # OpenCV Fallback
        cap = cv2.VideoCapture(str(path))
        if cap.isOpened():
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            cap_fps = float(cap.get(cv2.CAP_PROP_FPS))
            frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = (frames / cap_fps) if cap_fps > 0 and frames > 0 else 0.0
            cap.release()

            return MediaMetadata(
                file_path=str(path),
                storage_uri=file_uri,
                sha256=sha256_sum,
                duration_seconds=round(duration, 3) if duration else 0.0,
                media_type="video",
                file_size_bytes=file_size,
                width=w if w > 0 else None,
                height=h if h > 0 else None,
                fps=round(cap_fps, 3) if cap_fps > 0 else None,
                frame_count=frames if frames > 0 else None,
                has_video=True,
                has_audio=False,
            )

        # Image check
        img = cv2.imread(str(path))
        if img is not None:
            h, w = img.shape[:2]
            return MediaMetadata(
                file_path=str(path),
                storage_uri=file_uri,
                sha256=sha256_sum,
                duration_seconds=0.0,
                media_type="image",
                file_size_bytes=file_size,
                width=w,
                height=h,
                has_video=False,
                has_audio=False,
            )

        raise ValueError(f"Unable to decode or probe media file: {path}")

    @classmethod
    def to_media_asset(
        cls,
        metadata: MediaMetadata,
        media_asset_id: str | None = None,
        camera_id: str | None = None,
        storage_uri: str | None = None,
        recorded_at: datetime | None = None,
    ) -> MediaAsset:
        """Populate a valid MediaAsset domain model from extracted metadata."""
        asset_id = media_asset_id or f"media-{uuid.uuid4().hex[:8]}"
        uri = storage_uri or metadata.storage_uri
        duration = metadata.duration_seconds if metadata.duration_seconds > 0 else None
        if duration is not None and not math.isfinite(duration):
            duration = None

        return MediaAsset(
            media_asset_id=asset_id,
            media_type=metadata.media_type,
            storage_uri=uri,
            camera_id=camera_id,
            duration_seconds=duration,
            recorded_at=recorded_at,
            sha256=metadata.sha256,
            width=metadata.width,
            height=metadata.height,
            fps=metadata.fps,
            audio_sample_rate=metadata.audio_sample_rate,
        )

    @classmethod
    def create_camera(
        cls,
        camera_id: str,
        name: str,
        location_label: str | None = None,
        timezone: str | None = None,
        clock_offset_seconds: float | None = None,
    ) -> Camera:
        """Create a validated Camera domain model."""
        return Camera(
            camera_id=camera_id,
            name=name,
            location_label=location_label,
            timezone=timezone,
            clock_offset_seconds=clock_offset_seconds,
        )


def extract_media_metadata(file_path: str | Path) -> MediaMetadata:
    """Convenience function to extract metadata from a physical media file."""
    return MediaMetadataExtractor.extract(file_path)
