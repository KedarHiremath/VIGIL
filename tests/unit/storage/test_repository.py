"""Tests for InvestigationRepository and referential checks."""

import pytest

from vigil.domain.camera import Camera
from vigil.domain.media_asset import MediaAsset
from vigil.storage.repository import (
    EntityNotFoundError,
    InvestigationRepository,
    ReferentialIntegrityError,
)


def test_repository_media_asset_and_camera() -> None:
    repo = InvestigationRepository()

    cam = Camera(camera_id="cam-001", name="Front Gate Camera")
    repo.add_camera(cam)
    assert repo.get_camera("cam-001").name == "Front Gate Camera"

    asset = MediaAsset(
        media_asset_id="media-001",
        media_type="video",
        storage_uri="file:///media/feed1.mp4",
        camera_id="cam-001",
        duration_seconds=60.0,
    )
    repo.add_media_asset(asset)
    assert repo.get_media_asset("media-001").duration_seconds == 60.0


def test_repository_missing_entity_raises() -> None:
    repo = InvestigationRepository()
    with pytest.raises(EntityNotFoundError):
        repo.get_camera("non-existent-cam")


def test_repository_referential_integrity() -> None:
    repo = InvestigationRepository()
    asset = MediaAsset(
        media_asset_id="media-001",
        media_type="video",
        storage_uri="file:///media/feed1.mp4",
    )
    repo.add_media_asset(asset)

    # Valid check
    repo.validate_references_exist(["media-001"], expected_type="media_asset")

    # Invalid check
    with pytest.raises(ReferentialIntegrityError):
        repo.validate_references_exist(["media-missing"], expected_type="media_asset")


def test_repository_list_investigations() -> None:
    from vigil.domain.investigation import Investigation

    repo = InvestigationRepository()
    assert repo.list_investigations() == []

    inv1 = Investigation(
        investigation_id="inv-1",
        title="Inv 1",
        objective="Obj 1",
        scope_description="Scope 1",
    )
    repo.add_investigation(inv1)
    assert len(repo.list_investigations()) == 1
    assert repo.list_investigations()[0].investigation_id == "inv-1"
