from pathlib import Path

import pytest
from starlette.testclient import TestClient

from vigil.api.app import create_app
from vigil.api.dependencies import get_investigation_service, get_telemetry_manager
from vigil.models.mock import MockLLMClient
from vigil.services.investigation_service import InvestigationService
from vigil.services.telemetry import TelemetryManager
from vigil.storage.sqlite_repository import SqliteInvestigationRepository


@pytest.fixture
def media_setup(tmp_path: Path):
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
        yield client, service, tmp_path
    finally:
        service.shutdown(wait=False)


def test_create_demo_and_media_streaming(media_setup):
    client, _service, _ = media_setup

    # 1. Create demo case
    res_demo = client.post("/api/v1/investigations/demo")
    assert res_demo.status_code == 201
    data = res_demo.json()
    inv_id = data["investigation_id"]
    assert inv_id.startswith("inv-demo-")
    assert data["status"] == "completed"
    assert data["frame_count"] > 0
    assert data["has_audio"] is True

    # 2. Get media assets list
    res_media = client.get(f"/api/v1/investigations/{inv_id}/media")
    assert res_media.status_code == 200
    media_list = res_media.json()
    assert len(media_list) >= 1
    media_asset_id = media_list[0]["media_asset_id"]

    # 3. Stream primary media
    res_stream_prim = client.get(f"/api/v1/investigations/{inv_id}/media/primary/content")
    assert res_stream_prim.status_code == 200
    assert "video/mp4" in res_stream_prim.headers["content-type"]
    assert len(res_stream_prim.content) > 0

    # 4. Stream by media asset ID
    res_stream_id = client.get(f"/api/v1/investigations/{inv_id}/media/{media_asset_id}/content")
    assert res_stream_id.status_code == 200
    assert "video/mp4" in res_stream_id.headers["content-type"]

    # 5. Get evidence assessments
    res_assess = client.get(f"/api/v1/investigations/{inv_id}/assessments")
    assert res_assess.status_code == 200
    assess_list = res_assess.json()
    assert len(assess_list) >= 1
    assert "assessment_type" in assess_list[0]
