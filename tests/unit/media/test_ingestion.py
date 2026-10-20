"""Unit tests for MediaIngestionService."""

from pathlib import Path

from tests.media_test_helpers import create_test_video
from vigil.media.ingestion import MediaIngestionService
from vigil.storage.repository import InvestigationRepository


def test_media_ingestion_service_e2e(tmp_path: Path) -> None:
    repo = InvestigationRepository()
    service = MediaIngestionService(repository=repo)

    video_path = tmp_path / "camera_feed.mp4"
    create_test_video(video_path, duration_seconds=2.0, fps=24, with_audio=True)

    result = service.ingest_file(
        file_path=video_path,
        media_asset_id="media-cctv-1",
        camera_id="cam-gate-north",
        camera_name="North Gate Camera",
        output_artifacts_dir=tmp_path / "artifacts",
        sample_interval_seconds=0.5,
        max_frames=4,
        extract_audio=True,
    )

    # 1. Verify MediaAsset was stored in repository
    asset = repo.get_media_asset("media-cctv-1")
    assert asset.camera_id == "cam-gate-north"
    assert asset.media_type == "video"
    assert asset.duration_seconds is not None
    assert asset.duration_seconds > 0
    assert len(asset.sha256 or "") == 64

    # 2. Verify Camera was stored in repository
    camera = repo.get_camera("cam-gate-north")
    assert camera.name == "North Gate Camera"

    # 3. Verify Artifacts in repository
    assert len(result.frame_artifacts) > 0
    for art in result.frame_artifacts:
        stored_art = repo.get_artifact(art.artifact_id)
        assert stored_art.artifact_type == "frame"
        assert stored_art.media_type == "image"
        assert Path(stored_art.storage_uri.replace("file:///", "")).is_file()

    assert len(result.audio_artifacts) > 0
    for a_art in result.audio_artifacts:
        stored_audio = repo.get_artifact(a_art.artifact_id)
        assert stored_audio.artifact_type == "audio_segment"
        assert stored_audio.media_type == "audio"
