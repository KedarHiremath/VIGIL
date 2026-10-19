"""End-to-end tests for the LeadInvestigatorAgent and InvestigationPlanner."""

from vigil.agent.investigator import LeadInvestigatorAgent
from vigil.agent.planner import InvestigationPlanner
from vigil.domain.investigation import Investigation
from vigil.domain.media_asset import MediaAsset
from vigil.models.mock import MockLLMClient
from vigil.orchestration.investigation_state import InvestigationStatus
from vigil.storage.repository import InvestigationRepository


def test_investigation_planner() -> None:
    planner = InvestigationPlanner()
    inv = Investigation(
        investigation_id="inv-plan-001",
        title="Unauthorized Gate Entry Investigation",
        objective="Determine identity and timing of unauthorized entry",
        scope_description="Gate camera feed from 10:00 to 10:15 UTC",
        media_asset_ids=["media-asset-1"],
    )
    tasks = planner.plan_investigation(inv)
    assert len(tasks) >= 6
    task_types = [t.task_type for t in tasks]
    assert "frame_sampling" in task_types
    assert "visual_analysis" in task_types
    assert "event_correlation" in task_types
    assert "report_generation" in task_types


def test_lead_investigator_agent_full_run() -> None:
    repo = InvestigationRepository()
    mock_llm = MockLLMClient()

    # Pre-populate media asset
    asset = MediaAsset(
        media_asset_id="media-cam-north-01",
        media_type="video",
        storage_uri="file:///media/storage/gate_cam.mp4",
        duration_seconds=20.0,
    )
    repo.add_media_asset(asset)

    agent = LeadInvestigatorAgent(
        repository=repo,
        llm_client=mock_llm,
    )

    inv = Investigation(
        investigation_id="inv-live-001",
        title="Perimeter Breach at North Gate",
        objective="Verify perimeter breach and identify associated entities",
        scope_description="North gate camera feed recorded at 2026-10-19T22:00:00Z",
        media_asset_ids=["media-cam-north-01"],
        created_by="officer-smith",
    )

    outcome = agent.run_investigation(inv)

    # Assert investigation completed successfully
    assert outcome.state.status == InvestigationStatus.COMPLETED
    assert outcome.state.started_at is not None
    assert outcome.state.completed_at is not None
    assert len(outcome.task_results) > 0

    # Verify findings were recorded in state and repository
    assert len(outcome.state.task_ids) == len(outcome.task_results)
    assert len(outcome.state.observation_ids) > 0
    assert len(outcome.state.event_ids) > 0

    # Verify final report
    assert outcome.report is not None
    assert outcome.report.investigation_id == "inv-live-001"
    assert len(outcome.report.observation_ids) > 0
    assert len(outcome.report.event_ids) > 0
    assert len(outcome.report.assessment_ids) > 0
    assert len(outcome.report.coverage_ids) > 0
    assert outcome.report.summary != ""
