from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from vigil.domain.artifact import Artifact
from vigil.domain.camera import Camera
from vigil.domain.media_asset import MediaAsset
from vigil.domain.source_reference import SourceReference


def test_camera_accepts_valid_metadata() -> None:
    camera = Camera(
        camera_id="cam_001",
        name="Parking Entrance",
        timezone="Asia/Kolkata",
        clock_offset_seconds=0.0,
    )

    assert camera.camera_id == "cam_001"


def test_camera_rejects_unknown_timezone() -> None:
    with pytest.raises(ValidationError):
        Camera(
            camera_id="cam_001",
            name="Parking Entrance",
            timezone="Not/A_Timezone",
        )


def test_media_asset_rejects_invalid_checksum() -> None:
    with pytest.raises(ValidationError):
        MediaAsset(
            media_asset_id="media_001",
            media_type="video",
            storage_uri="file:///recording.mp4",
            sha256="invalid",
        )


def test_media_asset_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        MediaAsset(
            media_asset_id="media_001",
            media_type="video",
            storage_uri="file:///recording.mp4",
            recorded_at=datetime(2026, 10, 14, 10, 0),
        )


def test_source_reference_rejects_invalid_interval() -> None:
    with pytest.raises(ValidationError):
        SourceReference(
            media_asset_id="media_001",
            start_seconds=15.0,
            end_seconds=10.0,
        )


def test_source_reference_accepts_valid_interval() -> None:
    reference = SourceReference(
        media_asset_id="media_001",
        start_seconds=10.0,
        end_seconds=15.0,
        source_timestamp=datetime(
            2026, 10, 14, 10, 0, tzinfo=timezone.utc
        ),
    )

    assert reference.end_seconds > reference.start_seconds


def test_artifact_rejects_incompatible_media_type() -> None:
    with pytest.raises(ValidationError):
        Artifact(
            artifact_id="artifact_001",
            artifact_type="frame",
            media_type="video",
            storage_uri="file:///frame.mp4",
            source_reference=SourceReference(
                media_asset_id="media_001",
                start_seconds=10.0,
                end_seconds=11.0,
            ),
        )


def test_artifact_accepts_valid_frame() -> None:
    artifact = Artifact(
        artifact_id="artifact_001",
        artifact_type="frame",
        media_type="image",
        storage_uri="file:///frame.jpg",
        source_reference=SourceReference(
            media_asset_id="media_001",
            start_seconds=10.0,
            end_seconds=11.0,
        ),
    )

    assert artifact.artifact_type == "frame"
    assert artifact.media_type == "image"


def test_unexpected_fields_are_rejected() -> None:
    with pytest.raises(ValidationError):
        Camera(
            camera_id="cam_001",
            name="Parking Entrance",
            unexpected_field="not_allowed",
        )