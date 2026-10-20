"""Unit tests for SqliteInvestigationRepository persistence and restart recovery."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from vigil.domain.artifact import Artifact
from vigil.domain.camera import Camera
from vigil.domain.entity import Entity
from vigil.domain.event import Event
from vigil.domain.investigation import Investigation
from vigil.domain.media_asset import MediaAsset
from vigil.domain.observation import Observation
from vigil.domain.provenance import Provenance
from vigil.domain.source_reference import SourceReference
from vigil.orchestration.investigation_state import (
    InvestigationState,
    InvestigationStatus,
)
from vigil.storage.repository import (
    EntityNotFoundError,
    ReferentialIntegrityError,
)
from vigil.storage.sqlite_repository import SqliteInvestigationRepository


def test_sqlite_repository_camera_and_media_asset() -> None:
    repo = SqliteInvestigationRepository(":memory:")

    cam = Camera(camera_id="cam-001", name="West Entrance", timezone="UTC")
    repo.add_camera(cam)

    fetched_cam = repo.get_camera("cam-001")
    assert fetched_cam.name == "West Entrance"
    assert fetched_cam.timezone == "UTC"

    asset = MediaAsset(
        media_asset_id="media-001",
        media_type="video",
        storage_uri="file:///cctv/cam1.mp4",
        camera_id="cam-001",
        duration_seconds=120.0,
        sha256="a" * 64,
        width=1920,
        height=1080,
        fps=30.0,
    )
    repo.add_media_asset(asset)

    fetched_asset = repo.get_media_asset("media-001")
    assert fetched_asset.duration_seconds == 120.0
    assert fetched_asset.width == 1920
    assert fetched_asset.height == 1080
    assert fetched_asset.fps == 30.0
    assert len(repo.list_media_assets()) == 1


def test_sqlite_repository_persistence_across_restarts(tmp_path: Path) -> None:
    db_file = tmp_path / "vigil_investigation.db"
    now = datetime.now(UTC)

    # 1. First session: insert data
    with SqliteInvestigationRepository(db_file) as repo1:
        cam = Camera(camera_id="cam-002", name="Lobby")
        repo1.add_camera(cam)

        asset = MediaAsset(
            media_asset_id="media-002",
            media_type="video",
            storage_uri="file:///media/lobby.mp4",
            camera_id="cam-002",
            duration_seconds=45.0,
        )
        repo1.add_media_asset(asset)

        source_ref = SourceReference(
            media_asset_id="media-002",
            start_seconds=10.0,
            end_seconds=15.0,
        )
        art = Artifact(
            artifact_id="art-001",
            artifact_type="frame",
            media_type="image",
            storage_uri="file:///artifacts/lobby_f1.jpg",
            source_reference=source_ref,
        )
        repo1.add_artifact(art)

        prov = Provenance(
            producer_type="vision_model",
            producer_name="test_detector",
            method="unit_test",
        )
        obs = Observation(
            observation_id="obs-001",
            modality="image",
            observation_type="detection",
            description="Person entering lobby",
            source_references=[source_ref],
            confidence=0.92,
            provenance=prov,
        )
        repo1.add_observation(obs)

        ent = Entity(
            entity_id="ent-001",
            entity_type="person",
            label="Suspicious individual",
            associated_observation_ids=["obs-001"],
        )
        repo1.add_entity(ent)

        evt = Event(
            event_id="evt-001",
            event_type="entrance",
            description="Person entering lobby",
            observation_ids=["obs-001"],
            status="confirmed",
        )
        repo1.add_event(evt)

        inv = Investigation(
            investigation_id="inv-001",
            title="Lobby Security Incident",
            objective="Identify unauthorized individuals in lobby",
            scope_description="Footage from lobby camera between 10s and 45s",
        )
        repo1.add_investigation(inv)

        from vigil.domain.coverage import CoverageRecord, CoverageStatus
        cov = CoverageRecord(
            coverage_id="cov-001",
            investigation_id="inv-001",
            source_reference_id="ref-001",
            status=CoverageStatus.EXAMINED,
            examined_at=now,
        )
        repo1.add_coverage_record(cov)

        state = InvestigationState(
            investigation_id="inv-001",
            status=InvestigationStatus.RUNNING,
            task_ids=["task-1"],
            observation_ids=["obs-001"],
            event_ids=["evt-001"],
            started_at=now,
        )
        repo1.save_state(state)

    # 2. Second session: re-open DB and verify data persisted across restart
    with SqliteInvestigationRepository(db_file) as repo2:
        assert repo2.get_camera("cam-002").name == "Lobby"
        assert repo2.get_media_asset("media-002").duration_seconds == 45.0
        assert repo2.get_artifact("art-001").artifact_type == "frame"
        assert repo2.get_observation("obs-001").confidence == 0.92
        assert repo2.get_entity("ent-001").label == "Suspicious individual"
        assert repo2.get_event("evt-001").event_type == "entrance"
        assert repo2.get_investigation("inv-001").title == "Lobby Security Incident"
        assert len(repo2.list_coverage_records("inv-001")) == 1

        state2 = repo2.get_state("inv-001")
        assert state2 is not None
        assert state2.status == InvestigationStatus.RUNNING
        assert state2.event_ids == ["evt-001"]


def test_sqlite_referential_integrity() -> None:
    repo = SqliteInvestigationRepository(":memory:")
    asset = MediaAsset(
        media_asset_id="media-100",
        media_type="video",
        storage_uri="file:///cctv/test.mp4",
    )
    repo.add_media_asset(asset)

    # Valid check
    repo.validate_references_exist(["media-100"], expected_type="media_asset")

    # Missing check
    with pytest.raises(ReferentialIntegrityError):
        repo.validate_references_exist(["missing-media"], expected_type="media_asset")


def test_sqlite_missing_entity_raises() -> None:
    repo = SqliteInvestigationRepository(":memory:")
    with pytest.raises(EntityNotFoundError):
        repo.get_camera("unknown-cam")


def test_sqlite_list_investigations() -> None:
    repo = SqliteInvestigationRepository(":memory:")
    assert repo.list_investigations() == []

    inv = Investigation(
        investigation_id="inv-sql-1",
        title="SQL Inv 1",
        objective="Objective 1",
        scope_description="Scope 1",
    )
    repo.add_investigation(inv)
    invs = repo.list_investigations()
    assert len(invs) == 1
    assert invs[0].investigation_id == "inv-sql-1"
