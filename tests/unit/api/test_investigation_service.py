"""Unit tests for InvestigationService and TelemetryManager."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests.media_test_helpers import create_test_video
from vigil.models.mock import MockLLMClient
from vigil.orchestration.investigation_state import InvestigationStatus
from vigil.services.investigation_service import InvestigationService
from vigil.services.telemetry import TelemetryManager
from vigil.storage.repository import EntityNotFoundError
from vigil.storage.sqlite_repository import SqliteInvestigationRepository


def test_telemetry_manager_broadcast_and_history() -> None:
    telemetry = TelemetryManager(history_maxlen=10)
    inv_id = "inv-test-telemetry"

    # Broadcast events
    telemetry.broadcast(inv_id, "test_event_1", {"msg": "hello"})
    telemetry.broadcast(inv_id, "test_event_2", {"msg": "world"})

    history = telemetry.get_history(inv_id)
    assert len(history) == 2
    assert history[0]["event_type"] == "test_event_1"
    assert history[0]["data"]["msg"] == "hello"
    assert history[1]["event_type"] == "test_event_2"

    # Callback generator
    cb = telemetry.create_callback(inv_id)
    cb("callback_event", {"status": "ok"})
    history3 = telemetry.get_history(inv_id)
    assert len(history3) == 3
    assert history3[2]["event_type"] == "callback_event"


def test_investigation_service_lifecycle_sync(tmp_path: Path) -> None:
    video_path = tmp_path / "service_test.mp4"
    create_test_video(video_path, duration_seconds=1.5, fps=24, with_audio=True)

    repo = SqliteInvestigationRepository(":memory:")
    telemetry = TelemetryManager()
    service = InvestigationService(
        repository=repo,
        telemetry=telemetry,
        storage_dir=tmp_path / "storage",
        orchestrator=None,  # defaults with mock LLM if not configured
    )
    # Ensure orchestrator uses mock LLM for testing
    service.orchestrator.llm = MockLLMClient()

    # 1. Create and ingest
    inv, result = service.create_and_ingest_investigation(
        file_path=video_path,
        title="Service Unit Test Investigation",
        objective="Verify service lifecycle",
        scope_description="Testing sync investigation execution",
        camera_id="cam-service-01",
        sample_interval_seconds=0.5,
        max_frames=4,
    )

    assert inv.investigation_id.startswith("inv-")
    assert result.media_asset.media_asset_id.startswith("media-")
    assert len(result.frame_artifacts) > 0

    # Status right after creation
    status_created = service.get_status(inv.investigation_id)
    assert status_created.status == InvestigationStatus.CREATED
    assert status_created.has_report is False
    assert status_created.completed_tasks == 0

    # 2. Run investigation synchronously
    outcome = service.run_investigation(inv.investigation_id, run_async=False)
    assert outcome is not None
    assert outcome.state.status == InvestigationStatus.COMPLETED
    assert outcome.report is not None

    # Status after completion
    status_done = service.get_status(inv.investigation_id)
    assert status_done.status == InvestigationStatus.COMPLETED
    assert status_done.has_report is True
    assert status_done.observation_count > 0
    assert status_done.event_count > 0
    assert status_done.coverage_count > 0

    # 3. Retrieve report
    report = service.get_report(inv.investigation_id)
    assert report is not None
    assert report.investigation_id == inv.investigation_id

    # 4. Query entities
    obs_list = service.get_observations(inv.investigation_id)
    assert len(obs_list) > 0
    evt_list = service.get_events(inv.investigation_id)
    assert len(evt_list) > 0
    cov_list = service.get_coverage_records(inv.investigation_id)
    assert len(cov_list) > 0
    art_list = service.get_artifacts(inv.investigation_id)
    assert len(art_list) > 0

    # 5. List investigations
    invs = service.list_investigations()
    assert len(invs) == 1
    assert invs[0].investigation_id == inv.investigation_id

    service.shutdown()


def test_investigation_service_async_execution(tmp_path: Path) -> None:
    video_path = tmp_path / "async_test.mp4"
    create_test_video(video_path, duration_seconds=1.0, fps=24, with_audio=False)

    repo = SqliteInvestigationRepository(":memory:")
    telemetry = TelemetryManager()
    service = InvestigationService(
        repository=repo,
        telemetry=telemetry,
        storage_dir=tmp_path / "storage",
    )
    service.orchestrator.llm = MockLLMClient()

    inv, _ = service.create_and_ingest_investigation(
        file_path=video_path,
        title="Async Test Investigation",
        sample_interval_seconds=0.5,
        max_frames=3,
    )

    # Run async
    service.run_investigation(inv.investigation_id, run_async=True)

    # Wait for completion (up to 15s)
    deadline = time.time() + 15.0
    completed = False
    while time.time() < deadline:
        st = service.get_status(inv.investigation_id)
        if st.status == InvestigationStatus.COMPLETED:
            completed = True
            break
        time.sleep(0.2)

    assert completed is True
    status_done = service.get_status(inv.investigation_id)
    assert status_done.has_report is True

    service.shutdown()


def test_investigation_service_errors(tmp_path: Path) -> None:
    repo = SqliteInvestigationRepository(":memory:")
    service = InvestigationService(repository=repo)

    with pytest.raises(FileNotFoundError):
        service.create_and_ingest_investigation(
            file_path=tmp_path / "non_existent.mp4"
        )

    with pytest.raises(EntityNotFoundError):
        service.get_status("unknown-inv-id")

    with pytest.raises(EntityNotFoundError):
        service.get_report("unknown-inv-id")

    service.shutdown()


def test_investigation_service_multi_video_sequential_ingestion(tmp_path: Path) -> None:
    video_path_1 = tmp_path / "feed_north.mp4"
    video_path_2 = tmp_path / "feed_courtyard.mp4"
    create_test_video(video_path_1, duration_seconds=1.0, fps=24, with_audio=False)
    create_test_video(video_path_2, duration_seconds=1.0, fps=24, with_audio=False)

    repo = SqliteInvestigationRepository(":memory:")
    telemetry = TelemetryManager()
    service = InvestigationService(
        repository=repo,
        telemetry=telemetry,
        storage_dir=tmp_path / "storage",
    )
    service.orchestrator.llm = MockLLMClient()

    # Ingest multiple premise video feeds sequentially
    inv, composite_result = service.create_and_ingest_investigation(
        file_paths=[video_path_1, video_path_2],
        camera_ids=["cam-north-01", "cam-courtyard-02"],
        title="Multi-Feed Premise Breach Investigation",
        objective="Correlate timeline across all premise cameras",
        max_frames=4,
    )

    assert inv.investigation_id.startswith("inv-")
    assert len(composite_result.all_ingestion_results) == 2
    assert composite_result.media_asset.camera_id == "cam-north-01"
    assert composite_result.additional_results[0].media_asset.camera_id == "cam-courtyard-02"

    # Verify both MediaAssets registered under the investigation
    assets = service.get_media_assets(inv.investigation_id)
    assert len(assets) == 2
    cam_ids = {a.camera_id for a in assets}
    assert cam_ids == {"cam-north-01", "cam-courtyard-02"}

    # Run investigation across multiple feeds
    outcome = service.run_investigation(inv.investigation_id, run_async=False)
    assert outcome is not None
    assert outcome.state.status == InvestigationStatus.COMPLETED
    assert outcome.report is not None

    # Verify observations and coverage records cover both feeds
    obs = service.get_observations(inv.investigation_id)
    assert len(obs) > 0
    cov = service.get_coverage_records(inv.investigation_id)
    assert len(cov) >= 2

    # Add a 3rd camera feed dynamically to the existing investigation
    video_path_3 = tmp_path / "feed_gate.mp4"
    create_test_video(video_path_3, duration_seconds=1.0, fps=24, with_audio=False)
    res_3 = service.add_and_ingest_media(
        inv.investigation_id,
        file_path=video_path_3,
        camera_id="cam-gate-03",
        max_frames=2,
    )
    assert res_3.media_asset.camera_id == "cam-gate-03"

    # Verify service now reports 3 feeds for this investigation
    assets_after = service.get_media_assets(inv.investigation_id)
    assert len(assets_after) == 3

    service.shutdown()
