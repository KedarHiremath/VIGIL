"""Unit tests for specialized forensic agents."""

from vigil.agent.registry import create_default_executor
from vigil.agent.specialized import (
    AudioAgent,
    EvidenceVerificationAgent,
    ReportWriterAgent,
    TemporalCorrelationAgent,
    VisualAgent,
)
from vigil.domain.investigation import Investigation
from vigil.domain.media_asset import MediaAsset
from vigil.models.mock import MockLLMClient
from vigil.orchestration.investigation_state import (
    InvestigationState,
    InvestigationStatus,
)
from vigil.orchestration.service import OrchestrationService
from vigil.orchestration.task_types import TaskStatus
from vigil.storage.repository import InvestigationRepository


def setup_forensic_environment() -> tuple[
    InvestigationRepository, OrchestrationService, InvestigationState, MediaAsset
]:
    repo = InvestigationRepository()
    mock_llm = MockLLMClient()
    executor = create_default_executor(repository=repo, llm_client=mock_llm)
    service = OrchestrationService(executor=executor)

    asset = MediaAsset(
        media_asset_id="media-test-001",
        media_type="video",
        storage_uri="file:///storage/video.mp4",
        duration_seconds=20.0,
    )
    repo.add_media_asset(asset)

    inv = Investigation(
        investigation_id="inv-spec-001",
        title="Test Investigation",
        objective="Verify specialized agents",
        scope_description="Testing timeline",
        media_asset_ids=["media-test-001"],
    )
    repo.add_investigation(inv)

    state = InvestigationState(
        investigation_id="inv-spec-001",
        status=InvestigationStatus.CREATED,
    )
    repo.save_state(state)

    return repo, service, state, asset


def test_visual_and_audio_agents() -> None:
    repo, service, state, asset = setup_forensic_environment()

    # Visual agent
    vis_agent = VisualAgent(repository=repo, service=service)
    outcome_frames = vis_agent.extract_frames(
        state=state, media_asset_ids=[asset.media_asset_id], max_frames=3
    )
    assert outcome_frames.task_result.status == TaskStatus.COMPLETED
    assert len(outcome_frames.task_result.output_refs) > 0

    outcome_analysis = vis_agent.analyze_frames(
        state=outcome_frames.state,
        artifact_ids=outcome_frames.task_result.output_refs,
    )
    assert outcome_analysis.task_result.status == TaskStatus.COMPLETED
    assert len(outcome_analysis.task_result.output_refs) > 0

    # Audio agent
    audio_agent = AudioAgent(repository=repo, service=service)
    outcome_audio = audio_agent.analyze_audio(
        state=outcome_analysis.state, media_refs=[asset.media_asset_id]
    )
    assert outcome_audio.task_result.status == TaskStatus.COMPLETED
    assert len(outcome_audio.task_result.output_refs) > 0


def test_correlation_verification_and_report_agents() -> None:
    repo, service, state, asset = setup_forensic_environment()

    # Pre-populate visual frames & analysis
    vis_agent = VisualAgent(repository=repo, service=service)
    f_out = vis_agent.extract_frames(
        state=state, media_asset_ids=[asset.media_asset_id], max_frames=2
    )
    a_out = vis_agent.analyze_frames(
        state=f_out.state, artifact_ids=f_out.task_result.output_refs
    )

    # Correlation agent
    corr_agent = TemporalCorrelationAgent(repository=repo, service=service)
    c_out = corr_agent.correlate(
        state=a_out.state,
        observation_ids=a_out.task_result.output_refs,
    )
    assert c_out.task_result.status == TaskStatus.COMPLETED
    assert len(c_out.task_result.output_refs) > 0

    # Verification agent
    verif_agent = EvidenceVerificationAgent(repository=repo, service=service)
    v_out = verif_agent.verify_evidence(
        state=c_out.state,
        target_ids=c_out.task_result.output_refs,
    )
    assert v_out.task_result.status == TaskStatus.COMPLETED

    cov_out = verif_agent.evaluate_coverage(
        state=v_out.state,
        investigation_id="inv-spec-001",
        source_ref_ids=[asset.media_asset_id],
    )
    assert cov_out.task_result.status == TaskStatus.COMPLETED

    # Report writer agent
    rep_agent = ReportWriterAgent(repository=repo, service=service)
    r_out = rep_agent.generate_report(
        state=cov_out.state,
        investigation_id="inv-spec-001",
        title="Specialized Agent Report",
    )
    assert r_out.task_result.status == TaskStatus.COMPLETED
    report_id = r_out.task_result.output_refs[0]
    report = repo.get_report(report_id)
    assert report.investigation_id == "inv-spec-001"
    assert report.title == "Specialized Agent Report"
