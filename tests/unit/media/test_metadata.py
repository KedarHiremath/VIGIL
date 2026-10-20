"""Unit tests for media metadata extraction and model populator."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from tests.media_test_helpers import create_test_video, create_test_wav
from vigil.media.metadata import MediaMetadataExtractor, extract_media_metadata


def test_extract_metadata_video(tmp_path: Path) -> None:
    video_path = tmp_path / "sample.mp4"
    create_test_video(video_path, duration_seconds=1.5, fps=24, width=320, height=240, with_audio=True)

    metadata = extract_media_metadata(video_path)

    assert metadata.has_video is True
    assert metadata.width == 320
    assert metadata.height == 240
    assert metadata.fps is not None
    assert round(metadata.fps) == 24
    assert metadata.duration_seconds > 0.0
    assert len(metadata.sha256) == 64
    assert metadata.media_type == "video"
    assert metadata.file_size_bytes > 0


def test_extract_metadata_wav(tmp_path: Path) -> None:
    wav_path = tmp_path / "sample.wav"
    create_test_wav(wav_path, duration_seconds=1.0, sample_rate=16000)

    metadata = extract_media_metadata(wav_path)

    assert metadata.has_video is False
    assert metadata.has_audio is True
    assert metadata.audio_sample_rate == 16000
    assert metadata.audio_channels == 1
    assert metadata.duration_seconds > 0.0
    assert len(metadata.sha256) == 64
    assert metadata.media_type == "audio"


def test_metadata_to_media_asset_and_camera(tmp_path: Path) -> None:
    video_path = tmp_path / "sample.mp4"
    create_test_video(video_path, duration_seconds=2.0)

    metadata = extract_media_metadata(video_path)
    now = datetime.now(UTC)

    asset = MediaMetadataExtractor.to_media_asset(
        metadata=metadata,
        media_asset_id="media-sample-01",
        camera_id="cam-front-gate",
        recorded_at=now,
    )

    assert asset.media_asset_id == "media-sample-01"
    assert asset.camera_id == "cam-front-gate"
    assert asset.media_type == "video"
    assert asset.width == 320
    assert asset.height == 240
    assert asset.fps is not None
    assert asset.duration_seconds == metadata.duration_seconds
    assert asset.sha256 == metadata.sha256

    camera = MediaMetadataExtractor.create_camera(
        camera_id="cam-front-gate",
        name="Front Gate Camera",
        location_label="Main Gate",
        timezone="Asia/Kolkata",
    )

    assert camera.camera_id == "cam-front-gate"
    assert camera.name == "Front Gate Camera"
    assert camera.timezone == "Asia/Kolkata"


def test_extract_metadata_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        extract_media_metadata("non_existent_file.mp4")
