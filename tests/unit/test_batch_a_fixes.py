"""Unit tests verifying Batch A blocker bug fixes (A1, A2, A3, A4, A5)."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.media_test_helpers import create_test_video
from vigil.agent.planner import InvestigationPlanner
from vigil.config import config
from vigil.domain.artifact import Artifact
from vigil.domain.coverage import CoverageStatus
from vigil.domain.investigation import Investigation
from vigil.domain.media_asset import MediaAsset
from vigil.domain.source_reference import SourceReference
from vigil.media.decoder import MediaDecoder
from vigil.media.ingestion import MediaIngestionService
from vigil.media.metadata import MediaMetadataExtractor
from vigil.models.mock import MockLLMClient
from vigil.orchestration.task_types import TaskRequest
from vigil.storage.repository import InvestigationRepository
from vigil.tools.audio_transcriber import AudioTranscriberWorker
from vigil.tools.clip_slicer import ClipSlicerWorker
from vigil.tools.coverage_tracker import CoverageTrackerWorker
from vigil.tools.frame_extractor import FrameExtractorWorker
from vigil.tools.visual_detector import VisualDetectorWorker


def test_a1_a5_decoder_adaptive_interval_and_timestamps(tmp_path: Path) -> None:
    """A1 & A5: Verify decoder adapts interval across span and embeds timestamps in filenames."""
    video_path = tmp_path / "long_video.mp4"
    # Create 6.0 second video
    create_test_video(video_path, duration_seconds=6.0, fps=24, width=160, height=120)

    out_frames_dir = tmp_path / "frames_adaptive"
    # Request sample_interval_seconds=1.0, max_frames=3 across 6.0 seconds.
    # Without adaptive interval, it would only extract frames at 0s, 1s, 2s (truncating 3s-6s).
    # With adaptive interval, interval = 6.0 / 3 = 2.0s, covering 0s, 2s, 4s.
    frames = MediaDecoder.extract_frames(
        file_path=video_path,
        output_dir=out_frames_dir,
        sample_interval_seconds=1.0,
        start_seconds=0.0,
        end_seconds=6.0,
        max_frames=3,
    )

    assert len(frames) == 3
    # Verify timestamps are spread across the 6.0 second span
    assert frames[0].timestamp_seconds == pytest.approx(0.0, abs=0.2)
    assert frames[-1].timestamp_seconds >= 3.5

    # A5: Filenames should contain millisecond timestamp
    for f in frames:
        p = Path(f.file_path)
        assert p.is_file()
        assert p.name.startswith("frame_")
        assert p.name.endswith(".jpg")
        # Ensure timestamp ms format frame_{09d}.jpg
        ms_part = p.stem.replace("frame_", "")
        assert ms_part.isdigit()
        assert len(ms_part) == 9


def test_a1_visual_detector_evenly_spaced_selection() -> None:
    """A1: When frames exceed max_frames_per_task, select frames evenly across the timeline."""
    arts = []
    for i, t in enumerate([0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]):
        sr = SourceReference(media_asset_id="media-1", start_seconds=t, end_seconds=t + 1.0)
        art = Artifact(
            artifact_id=f"art-{i}",
            artifact_type="frame",
            media_type="image",
            storage_uri=f"file:///test/f_{i}.jpg",
            source_reference=sr,
        )
        arts.append(art)

    selected_ids = VisualDetectorWorker._select_evenly_spaced_artifacts(arts, limit=3)
    assert len(selected_ids) == 3
    # Evenly spaced: should pick first, middle, and last
    assert selected_ids[0] == "art-0"
    assert selected_ids[-1] == "art-9"


def test_a1_planner_derives_frames_from_duration() -> None:
    """A1: Planner derives max_frames from duration rather than constant 8."""
    repo = InvestigationRepository()
    asset = MediaAsset(
        media_asset_id="media-long",
        media_type="video",
        storage_uri="file:///test.mp4",
        duration_seconds=120.0,  # 120s / 2.0s = 60 frames
    )
    repo.add_media_asset(asset)
    inv = Investigation(
        investigation_id="inv-plan-test",
        title="Planning Test",
        objective="Test adaptive planning",
        scope_description="Testing",
        media_asset_ids=["media-long"],
    )
    repo.add_investigation(inv)

    planner = InvestigationPlanner(repository=repo)
    tasks = planner.plan_investigation(inv)

    frame_task = next(t for t in tasks if t.task_type == "frame_sampling")
    vis_task = next(t for t in tasks if t.task_type == "visual_analysis")

    # 120s @ 2.0s interval = 60 frames (capped by max_analysis_frames=100)
    assert frame_task.parameters["max_frames"] == 60
    assert vis_task.parameters["max_frames_per_task"] == 60


def test_a1_frame_extractor_reuses_existing_artifacts(tmp_path: Path) -> None:
    """A1: Frame extractor reuses existing frame artifacts rather than duplicating extraction."""
    repo = InvestigationRepository()
    asset = MediaAsset(
        media_asset_id="media-reuse",
        media_type="video",
        storage_uri="file:///fake.mp4",
        duration_seconds=20.0,
    )
    repo.add_media_asset(asset)

    # Ingestion already created an artifact
    sr = SourceReference(media_asset_id="media-reuse", start_seconds=2.0, end_seconds=4.0)
    existing_art = Artifact(
        artifact_id="art-existing-1",
        artifact_type="frame",
        media_type="image",
        storage_uri="file:///frames/existing.jpg",
        source_reference=sr,
    )
    repo.add_artifact(existing_art)

    worker = FrameExtractorWorker(repository=repo, llm_client=MockLLMClient())
    req = TaskRequest(
        task_id="task-frame-reuse",
        task_type="frame_sampling",
        input_refs=["media-reuse"],
        parameters={"start_seconds": 0.0, "end_seconds": 10.0, "max_frames": 5},
    )
    res = worker.run(req)

    # Reuses existing artifact ID
    assert "art-existing-1" in res


def test_a2_visual_detector_failed_vlm_creates_analysis_failed() -> None:
    """A2: Failed VLM call creates observation_type='analysis_failed' with confidence 0.0."""
    repo = InvestigationRepository()
    asset = MediaAsset(
        media_asset_id="media-fail",
        media_type="video",
        storage_uri="file:///test.mp4",
    )
    repo.add_media_asset(asset)
    sr = SourceReference(media_asset_id="media-fail", start_seconds=1.0, end_seconds=2.0)
    art = Artifact(
        artifact_id="art-fail-1",
        artifact_type="frame",
        media_type="image",
        storage_uri="file:///non_existent_file.jpg",  # Unresolvable URI
        source_reference=sr,
    )
    repo.add_artifact(art)

    # Real LLM mock that is not MockLLMClient to test real URI resolution check
    failing_llm = MagicMock()
    failing_llm.model_name = "test-failing-vlm"

    worker = VisualDetectorWorker(repository=repo, llm_client=failing_llm)
    req = TaskRequest(
        task_id="task-vis-fail",
        task_type="visual_analysis",
        input_refs=["art-fail-1"],
        parameters={},
    )
    obs_ids = worker.run(req)
    assert len(obs_ids) == 1

    obs = repo.get_observation(obs_ids[0])
    assert obs.observation_type == "analysis_failed"
    assert obs.confidence == 0.0
    assert "Visual inspection failed" in obs.description
    assert "Unresolvable storage URI" in obs.description


def test_a3_coverage_tracker_truthful_intervals_and_gaps() -> None:
    """A3: Coverage records reflect actual examined intervals and generate unexamined gaps."""
    repo = InvestigationRepository()
    # 100s video
    asset = MediaAsset(
        media_asset_id="media-cov",
        media_type="video",
        storage_uri="file:///video.mp4",
        duration_seconds=100.0,
        recorded_at=datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC),
    )
    repo.add_media_asset(asset)

    inv = Investigation(
        investigation_id="inv-cov-test",
        title="Coverage Test",
        objective="Verify truthful coverage",
        scope_description="Coverage testing",
        media_asset_ids=["media-cov"],
    )
    repo.add_investigation(inv)

    # Frame examined 10s-20s (10s total = 10% coverage)
    sr = SourceReference(media_asset_id="media-cov", start_seconds=10.0, end_seconds=20.0)
    art = Artifact(
        artifact_id="art-cov-1",
        artifact_type="frame",
        media_type="image",
        storage_uri="file:///frame.jpg",
        source_reference=sr,
    )
    repo.add_artifact(art)

    worker = CoverageTrackerWorker(repository=repo, llm_client=MockLLMClient())
    req = TaskRequest(
        task_id="task-cov-1",
        task_type="coverage_evaluation",
        input_refs=["media-cov"],
        parameters={"investigation_id": "inv-cov-test"},
    )
    cov_ids = worker.run(req)

    records = repo.list_coverage_records("inv-cov-test")
    # Should have 1 PARTIAL examined record and gaps (0-10s and 20-100s)
    partial_recs = [r for r in records if r.status == CoverageStatus.PARTIAL]
    gap_recs = [r for r in records if r.status == CoverageStatus.NOT_EXAMINED]

    assert len(partial_recs) == 1
    assert "10.0% total footage coverage" in partial_recs[0].notes
    assert len(gap_recs) >= 2  # leading gap 0-10s and trailing gap 20-100s


def test_a4_unknown_duration_not_clamped() -> None:
    """A4: Unknown duration does not silently become 60s/30s/10s."""
    repo = InvestigationRepository()
    asset = MediaAsset(
        media_asset_id="media-no-dur",
        media_type="video",
        storage_uri="file:///test.mp4",
        duration_seconds=None,  # Unknown duration
    )
    repo.add_media_asset(asset)

    # Clip slicer should fail with informative error when neither end_seconds nor duration is known
    slicer_worker = ClipSlicerWorker(repository=repo, llm_client=MockLLMClient())
    req = TaskRequest(
        task_id="task-clip-err",
        task_type="clip_slicing",
        input_refs=["media-no-dur"],
        parameters={},
    )
    with pytest.raises(ValueError, match="unknown duration"):
        slicer_worker.run(req)


def test_parse_confidence_qualitative_and_strings() -> None:
    """Verify parse_confidence handles qualitative strings, percentages, and floats."""
    from vigil.tools.visual_detector import parse_confidence

    assert parse_confidence(0.95) == 0.95
    assert parse_confidence("high") == 0.90
    assert parse_confidence("VERY HIGH") == 0.90
    assert parse_confidence("medium") == 0.75
    assert parse_confidence("moderate") == 0.75
    assert parse_confidence("low") == 0.50
    assert parse_confidence("0.88") == 0.88
    assert parse_confidence("85%") == 0.85
    assert parse_confidence(None, default=0.7) == 0.7
    assert parse_confidence("unknown_string", default=0.8) == 0.8


def test_visual_detector_handles_string_confidence() -> None:
    """Verify VisualDetectorWorker parses VLM response with string confidence ('high')."""
    import json
    repo = InvestigationRepository()
    asset = MediaAsset(
        media_asset_id="media-str-conf",
        media_type="video",
        storage_uri="file:///test.mp4",
    )
    repo.add_media_asset(asset)
    sr = SourceReference(media_asset_id="media-str-conf", start_seconds=0.0, end_seconds=2.0)
    art = Artifact(
        artifact_id="art-str-conf-1",
        artifact_type="frame",
        media_type="image",
        storage_uri="file:///test/f.jpg",
        source_reference=sr,
    )
    repo.add_artifact(art)

    mock_llm = MagicMock()
    mock_llm.model_name = "test-vlm"
    from vigil.models.base import LLMResponse
    mock_llm.analyze_image.return_value = LLMResponse(
        content=json.dumps({
            "observations": [
                {
                    "observation_type": "person_detection",
                    "description": "Person detected near entrance.",
                    "confidence": "high",  # String confidence from real NIM VLM
                }
            ]
        }),
        model_name="test-vlm",
    )

    worker = VisualDetectorWorker(repository=repo, llm_client=mock_llm)
    req = TaskRequest(
        task_id="task-str-conf",
        task_type="visual_analysis",
        input_refs=["art-str-conf-1"],
        parameters={},
    )
    # Storage URI is mock, so it falls back to analysis_failed unless URI is resolvable or mock
    # Let's test with http URI so it attempts analyze_image
    art_http = Artifact(
        artifact_id="art-str-conf-http",
        artifact_type="frame",
        media_type="image",
        storage_uri="http://example.com/frame.jpg",
        source_reference=sr,
    )
    repo.add_artifact(art_http)
    req_http = TaskRequest(
        task_id="task-str-conf-2",
        task_type="visual_analysis",
        input_refs=["art-str-conf-http"],
        parameters={},
    )
    obs_ids = worker.run(req_http)
    assert len(obs_ids) == 1
    obs = repo.get_observation(obs_ids[0])
    assert obs.confidence == 0.90
    assert obs.observation_type == "person_detection"

