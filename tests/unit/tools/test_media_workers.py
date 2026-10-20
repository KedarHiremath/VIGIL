"""Unit tests for media forensic workers."""

from pathlib import Path

from tests.media_test_helpers import create_test_video
from vigil.domain.media_asset import MediaAsset
from vigil.models.mock import MockLLMClient
from vigil.orchestration.task_types import TaskRequest, TaskStatus
from vigil.storage.repository import InvestigationRepository
from vigil.tools.clip_slicer import ClipSlicerWorker
from vigil.tools.frame_extractor import FrameExtractorWorker
from vigil.tools.media_ingestion import MediaIngestionWorker


def test_media_ingestion_worker(tmp_path: Path) -> None:
    repo = InvestigationRepository()
    worker = MediaIngestionWorker(repository=repo, llm_client=MockLLMClient())

    video_path = tmp_path / "incoming_feed.mp4"
    create_test_video(video_path, duration_seconds=1.5, fps=24)

    req = TaskRequest(
        task_id="task-ingest-1",
        task_type="media_ingestion",
        parameters={
            "file_path": str(video_path),
            "camera_id": "cam-101",
            "camera_name": "Lobby Main",
            "sample_interval_seconds": 0.5,
            "max_frames": 3,
        },
    )

    result = worker.execute(req)
    assert result.status == TaskStatus.COMPLETED
    assert len(result.output_refs) > 0

    media_id = result.output_refs[0]
    asset = repo.get_media_asset(media_id)
    assert asset.camera_id == "cam-101"

    # Frame artifacts should be present
    for art_id in result.output_refs[1:]:
        art = repo.get_artifact(art_id)
        assert art.artifact_type in {"frame", "audio_segment"}


def test_clip_slicer_worker_real_video(tmp_path: Path) -> None:
    repo = InvestigationRepository()
    worker = ClipSlicerWorker(repository=repo, llm_client=MockLLMClient())

    video_path = tmp_path / "surveillance.mp4"
    create_test_video(video_path, duration_seconds=3.0, fps=24)

    asset = MediaAsset(
        media_asset_id="media-cctv-2",
        media_type="video",
        storage_uri=video_path.as_uri(),
        duration_seconds=3.0,
    )
    repo.add_media_asset(asset)

    req = TaskRequest(
        task_id="task-slice-1",
        task_type="clip_slicing",
        parameters={
            "media_asset_id": "media-cctv-2",
            "start_seconds": 0.5,
            "end_seconds": 2.0,
            "output_dir": str(tmp_path / "sliced"),
        },
    )

    result = worker.execute(req)
    assert result.status == TaskStatus.COMPLETED
    assert len(result.output_refs) == 1

    art = repo.get_artifact(result.output_refs[0])
    assert art.artifact_type == "clip"
    assert art.media_type == "video"
    assert len(art.sha256 or "") == 64


def test_clip_slicer_worker_mock_fallback() -> None:
    repo = InvestigationRepository()
    worker = ClipSlicerWorker(repository=repo, llm_client=MockLLMClient())

    asset = MediaAsset(
        media_asset_id="media-mock-1",
        media_type="video",
        storage_uri="file:///virtual/footage.mp4",
        duration_seconds=20.0,
    )
    repo.add_media_asset(asset)

    req = TaskRequest(
        task_id="task-slice-mock",
        task_type="clip_slicing",
        parameters={
            "media_asset_id": "media-mock-1",
            "start_seconds": 2.0,
            "end_seconds": 5.0,
        },
    )

    result = worker.execute(req)
    assert result.status == TaskStatus.COMPLETED
    art = repo.get_artifact(result.output_refs[0])
    assert art.artifact_type == "clip"
    assert art.source_reference.start_seconds == 2.0
    assert art.source_reference.end_seconds == 5.0


def test_frame_extractor_with_real_video(tmp_path: Path) -> None:
    repo = InvestigationRepository()
    worker = FrameExtractorWorker(repository=repo, llm_client=MockLLMClient())

    video_path = tmp_path / "real_footage.mp4"
    create_test_video(video_path, duration_seconds=1.5, fps=24)

    asset = MediaAsset(
        media_asset_id="media-real-1",
        media_type="video",
        storage_uri=video_path.as_uri(),
        duration_seconds=1.5,
    )
    repo.add_media_asset(asset)

    req = TaskRequest(
        task_id="task-frames-real",
        task_type="frame_sampling",
        input_refs=["media-real-1"],
        parameters={"sample_interval_seconds": 0.5, "max_frames": 3},
    )

    result = worker.execute(req)
    assert result.status == TaskStatus.COMPLETED
    assert len(result.output_refs) > 0
    art = repo.get_artifact(result.output_refs[0])
    assert art.artifact_type == "frame"
    assert art.media_type == "image"
