"""Regression tests for investigation report lifecycle, status endpoints, and notification deduplication."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from tests.media_test_helpers import create_test_video
from vigil.api.app import create_app
from vigil.api.dependencies import (
    get_investigation_service,
    get_telemetry_manager,
)
from vigil.domain.entity import Entity
from vigil.domain.investigation import Investigation
from vigil.domain.observation import Observation
from vigil.domain.provenance import Provenance
from vigil.domain.report import Report
from vigil.domain.source_reference import SourceReference
from vigil.models.mock import MockLLMClient
from vigil.orchestration.investigation_state import (
    InvestigationState,
    InvestigationStatus,
)
from vigil.services.investigation_service import InvestigationService
from vigil.services.telemetry import TelemetryManager
from vigil.storage.sqlite_repository import SqliteInvestigationRepository


@pytest.fixture
def api_test_env(tmp_path: Path):
    """Isolated environment with in-memory SQLite repo and test client."""
    repo = SqliteInvestigationRepository(":memory:")
    telemetry = TelemetryManager()
    service = InvestigationService(
        repository=repo,
        telemetry=telemetry,
        storage_dir=tmp_path / "storage",
    )
    service.orchestrator.llm = MockLLMClient()

    app = create_app()
    app.dependency_overrides[get_investigation_service] = lambda: service
    app.dependency_overrides[get_telemetry_manager] = lambda: telemetry

    client = TestClient(app)
    try:
        yield client, service, repo, tmp_path
    finally:
        service.shutdown(wait=False)


def test_running_investigation_status_and_report_conflict(api_test_env) -> None:
    """When an investigation is RUNNING:
    - Status endpoint reports status='running' and has_report=False.
    - Calling /report returns 409 Conflict, indicating report is still processing (not a 404 failure).
    """
    client, service, repo, _ = api_test_env
    inv_id = "inv-run-01"

    inv = Investigation(
        investigation_id=inv_id,
        title="Active Investigation",
        objective="Verify perimeter security",
        scope_description="Testing running state",
        media_asset_ids=[],
    )
    repo.add_investigation(inv)
    state = InvestigationState(
        investigation_id=inv_id,
        status=InvestigationStatus.RUNNING,
    )
    repo.save_state(state)

    # 1. Status poll
    res_status = client.get(f"/api/v1/investigations/{inv_id}/status")
    assert res_status.status_code == 200
    data = res_status.json()
    assert data["status"] == "running"
    assert data["has_report"] is False
    assert data["report_id"] is None

    # 2. Report request during active run returns 409 Conflict (not a failure, normal lifecycle)
    res_report = client.get(f"/api/v1/investigations/{inv_id}/report")
    assert res_report.status_code == 409
    assert "still in status 'running'" in res_report.json()["detail"]


def test_completed_investigation_without_report_not_falsely_ready(api_test_env) -> None:
    """When an investigation reaches COMPLETED status without a persisted report:
    - Status reports has_report=False.
    - Calling /report returns 404 Not Found.
    - The investigation is NOT falsely reported as having a ready report.
    """
    client, service, repo, _ = api_test_env
    inv_id = "inv-comp-no-rep"

    inv = Investigation(
        investigation_id=inv_id,
        title="Completed Without Report",
        objective="Edge case test",
        scope_description="Testing completed without report",
        media_asset_ids=[],
    )
    repo.add_investigation(inv)
    state = InvestigationState(
        investigation_id=inv_id,
        status=InvestigationStatus.COMPLETED,
        completed_at=datetime.now(UTC),
    )
    repo.save_state(state)

    # Status check
    res_status = client.get(f"/api/v1/investigations/{inv_id}/status")
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "completed"
    assert res_status.json()["has_report"] is False

    # Report check
    res_report = client.get(f"/api/v1/investigations/{inv_id}/report")
    assert res_report.status_code == 404
    assert "No forensic report generated" in res_report.json()["detail"]


def test_failed_investigation_lifecycle(api_test_env) -> None:
    """When an investigation fails, status reflects failure and error message."""
    client, service, repo, _ = api_test_env
    inv_id = "inv-fail-01"

    inv = Investigation(
        investigation_id=inv_id,
        title="Failed Investigation",
        objective="Failure test",
        scope_description="Testing failed state",
        media_asset_ids=[],
    )
    repo.add_investigation(inv)
    state = InvestigationState(
        investigation_id=inv_id,
        status=InvestigationStatus.FAILED,
        completed_at=datetime.now(UTC),
    )
    repo.save_state(state)

    res_status = client.get(f"/api/v1/investigations/{inv_id}/status")
    assert res_status.status_code == 200
    assert res_status.json()["status"] == "failed"
    assert res_status.json()["has_report"] is False


def test_completed_investigation_with_report_and_entities_endpoint(api_test_env) -> None:
    """When report is persisted:
    - Status reports has_report=True and report_id.
    - /report endpoint successfully returns compiled report.
    - /entities endpoint returns strictly investigation-scoped entities without leaking outside records.
    """
    client, service, repo, _ = api_test_env
    inv_id = "inv-ready-01"
    other_inv_id = "inv-unrelated-02"

    # Investigation 1 (Target)
    inv = Investigation(
        investigation_id=inv_id,
        title="Ready Investigation",
        objective="Test ready state",
        scope_description="Testing report ready",
        media_asset_ids=["m1"],
    )
    repo.add_investigation(inv)

    obs1 = Observation(
        observation_id="obs-r1",
        modality="image",
        observation_type="person_detection",
        description="Person entering west entrance.",
        source_references=[SourceReference(media_asset_id="m1", start_seconds=1.0, end_seconds=2.0)],
        artifact_ids=["art-1"],
        confidence=0.95,
        provenance=Provenance(producer_type="vision_model", producer_name="vlm", method="detect"),
    )
    repo.add_observation(obs1)

    state = InvestigationState(
        investigation_id=inv_id,
        status=InvestigationStatus.COMPLETED,
        completed_at=datetime.now(UTC),
        observation_ids=[obs1.observation_id],
    )
    repo.save_state(state)

    ent1 = Entity(
        entity_id="ent-r1",
        entity_type="person",
        label="Suspect-Alpha",
        attributes={"clothing": "black hoodie"},
        associated_observation_ids=[obs1.observation_id],
    )
    repo.add_entity(ent1)

    rep = Report(
        report_id="rep-ready-01",
        investigation_id=inv_id,
        title="Official Completed Deliverable",
        summary="Analysis confirmed verified activity on west entrance.",
        generated_by="lead-agent",
        observation_ids=[obs1.observation_id],
    )
    repo.add_report(rep)

    # Investigation 2 (Unrelated - must NOT leak into inv_id)
    inv_other = Investigation(
        investigation_id=other_inv_id,
        title="Unrelated Other Case",
        objective="Other case",
        scope_description="Other scope",
        media_asset_ids=["m2"],
    )
    repo.add_investigation(inv_other)

    obs2 = Observation(
        observation_id="obs-other-02",
        modality="image",
        observation_type="vehicle_detection",
        description="Unrelated car in distant parking lot.",
        source_references=[SourceReference(media_asset_id="m2", start_seconds=10.0, end_seconds=15.0)],
        artifact_ids=["art-other"],
        confidence=0.88,
        provenance=Provenance(producer_type="vision_model", producer_name="vlm", method="detect"),
    )
    repo.add_observation(obs2)

    ent_other = Entity(
        entity_id="ent-other-car",
        entity_type="vehicle",
        label="Vehicle-Secret",
        attributes={"color": "red"},
        associated_observation_ids=[obs2.observation_id],
    )
    repo.add_entity(ent_other)

    state_other = InvestigationState(
        investigation_id=other_inv_id,
        status=InvestigationStatus.COMPLETED,
        completed_at=datetime.now(UTC),
        observation_ids=[obs2.observation_id],
    )
    repo.save_state(state_other)

    # 1. Status check for Target Investigation
    res_status = client.get(f"/api/v1/investigations/{inv_id}/status")
    assert res_status.status_code == 200
    assert res_status.json()["has_report"] is True
    assert res_status.json()["report_id"] == "rep-ready-01"

    # 2. Report retrieval
    res_report = client.get(f"/api/v1/investigations/{inv_id}/report")
    assert res_report.status_code == 200
    assert res_report.json()["report_id"] == "rep-ready-01"
    assert res_report.json()["title"] == "Official Completed Deliverable"

    # 3. Scoped Entities retrieval
    res_entities = client.get(f"/api/v1/investigations/{inv_id}/entities")
    assert res_entities.status_code == 200
    entities_data = res_entities.json()
    assert len(entities_data) == 1
    assert entities_data[0]["entity_id"] == "ent-r1"
    assert entities_data[0]["label"] == "Suspect-Alpha"
    # Ensure entity from other investigation does NOT leak!
    assert not any(e["entity_id"] == "ent-other-car" for e in entities_data)
