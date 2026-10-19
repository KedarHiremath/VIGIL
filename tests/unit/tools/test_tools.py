"""Unit tests for forensic tool workers."""

from vigil.domain.media_asset import MediaAsset
from vigil.models.mock import MockLLMClient
from vigil.orchestration.task_types import TaskRequest, TaskStatus
from vigil.storage.repository import InvestigationRepository
from vigil.tools.audio_transcriber import AudioTranscriberWorker
from vigil.tools.coverage_tracker import CoverageTrackerWorker
from vigil.tools.event_correlator import EventCorrelatorWorker
from vigil.tools.evidence_assessor import EvidenceAssessorWorker
from vigil.tools.frame_extractor import FrameExtractorWorker
from vigil.tools.report_generator import ReportGeneratorWorker
from vigil.tools.visual_detector import VisualDetectorWorker


def make_repo_with_media() -> tuple[InvestigationRepository, MediaAsset]:
    repo = InvestigationRepository()
    asset = MediaAsset(
        media_asset_id="media-001",
        media_type="video",
        storage_uri="file:///media/feed1.mp4",
        duration_seconds=30.0,
    )
    repo.add_media_asset(asset)
    return repo, asset


def test_frame_extractor_worker() -> None:
    repo, asset = make_repo_with_media()
    worker = FrameExtractorWorker(repository=repo, llm_client=MockLLMClient())

    req = TaskRequest(
        task_id="task-frame-1",
        task_type="frame_sampling",
        input_refs=[asset.media_asset_id],
        parameters={"sample_interval_seconds": 5.0, "max_frames": 4},
    )
    result = worker.execute(req)

    assert result.status == TaskStatus.COMPLETED
    assert len(result.output_refs) > 0
    # Verify artifacts exist in repo
    for art_id in result.output_refs:
        art = repo.get_artifact(art_id)
        assert art.artifact_type == "frame"
        assert art.media_type == "image"
        assert len(art.sha256 or "") == 64


def test_visual_detector_worker() -> None:
    repo, asset = make_repo_with_media()
    frame_worker = FrameExtractorWorker(repository=repo, llm_client=MockLLMClient())
    frame_res = frame_worker.execute(
        TaskRequest(
            task_id="task-frame-1",
            task_type="frame_sampling",
            input_refs=[asset.media_asset_id],
            parameters={"max_frames": 2},
        )
    )

    vis_worker = VisualDetectorWorker(repository=repo, llm_client=MockLLMClient())
    req = TaskRequest(
        task_id="task-vis-1",
        task_type="visual_analysis",
        input_refs=frame_res.output_refs,
        parameters={},
    )
    result = vis_worker.execute(req)

    assert result.status == TaskStatus.COMPLETED
    assert len(result.output_refs) > 0

    # Verify observations in repo
    obs = repo.get_observation(result.output_refs[0])
    assert obs.modality == "image"
    assert obs.provenance.producer_type == "vision_model"


def test_audio_transcriber_worker() -> None:
    repo, asset = make_repo_with_media()
    worker = AudioTranscriberWorker(repository=repo, llm_client=MockLLMClient())
    req = TaskRequest(
        task_id="task-aud-1",
        task_type="audio_transcription",
        input_refs=[asset.media_asset_id],
        parameters={},
    )
    result = worker.execute(req)
    assert result.status == TaskStatus.COMPLETED
    obs = repo.get_observation(result.output_refs[0])
    assert obs.modality == "audio"


def test_event_correlator_and_assessment() -> None:
    repo, asset = make_repo_with_media()
    # Populate frames & visual detections
    frame_worker = FrameExtractorWorker(repository=repo, llm_client=MockLLMClient())
    frame_res = frame_worker.execute(
        TaskRequest(
            task_id="task-frame-1",
            task_type="frame_sampling",
            input_refs=[asset.media_asset_id],
            parameters={"max_frames": 3},
        )
    )
    vis_worker = VisualDetectorWorker(repository=repo, llm_client=MockLLMClient())
    vis_res = vis_worker.execute(
        TaskRequest(
            task_id="task-vis-1",
            task_type="visual_analysis",
            input_refs=frame_res.output_refs,
            parameters={},
        )
    )

    corr_worker = EventCorrelatorWorker(repository=repo, llm_client=MockLLMClient())
    corr_res = corr_worker.execute(
        TaskRequest(
            task_id="task-corr-1",
            task_type="event_correlation",
            input_refs=vis_res.output_refs,
            parameters={},
        )
    )
    assert corr_res.status == TaskStatus.COMPLETED
    assert len(corr_res.output_refs) > 0

    # Assessment
    assess_worker = EvidenceAssessorWorker(repository=repo, llm_client=MockLLMClient())
    assess_res = assess_worker.execute(
        TaskRequest(
            task_id="task-asm-1",
            task_type="evidence_assessment",
            input_refs=corr_res.output_refs,
            parameters={},
        )
    )
    assert assess_res.status == TaskStatus.COMPLETED
    assert len(assess_res.output_refs) > 0


def test_coverage_and_report_generator() -> None:
    repo, asset = make_repo_with_media()
    cov_worker = CoverageTrackerWorker(repository=repo, llm_client=MockLLMClient())
    cov_res = cov_worker.execute(
        TaskRequest(
            task_id="task-cov-1",
            task_type="coverage_evaluation",
            input_refs=[asset.media_asset_id],
            parameters={"investigation_id": "inv-test-101"},
        )
    )
    assert cov_res.status == TaskStatus.COMPLETED

    rep_worker = ReportGeneratorWorker(repository=repo, llm_client=MockLLMClient())
    rep_res = rep_worker.execute(
        TaskRequest(
            task_id="task-rep-1",
            task_type="report_generation",
            input_refs=[],
            parameters={"investigation_id": "inv-test-101", "title": "Test Report"},
        )
    )
    assert rep_res.status == TaskStatus.COMPLETED
    report = repo.get_report(rep_res.output_refs[0])
    assert report.investigation_id == "inv-test-101"
    assert report.title == "Test Report"
