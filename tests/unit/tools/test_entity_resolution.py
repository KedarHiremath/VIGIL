"""Unit tests for conservative entity resolution in VisualDetectorWorker."""

import pytest
from pathlib import Path

from vigil.domain.entity import Entity
from vigil.domain.media_asset import MediaAsset
from vigil.domain.observation import Observation
from vigil.domain.provenance import Provenance
from vigil.domain.source_reference import SourceReference
from vigil.storage.repository import InvestigationRepository
from vigil.storage.sqlite_repository import SqliteInvestigationRepository
from vigil.tools.visual_detector import resolve_or_create_entity


@pytest.mark.parametrize("repo_type", ["in_memory", "sqlite"])
def test_repeated_entity_observations_reuse_entity_id(tmp_path: Path, repo_type: str) -> None:
    """Repeated detections of the same specific entity must reuse the same entity ID."""
    if repo_type == "sqlite":
        repo = SqliteInvestigationRepository(tmp_path / "test.db")
    else:
        repo = InvestigationRepository()

    active_entities: dict[str, Entity] = {}

    entity_info_1 = {
        "entity_type": "person",
        "label": "Suspect-1",
        "attributes": {"clothing_upper": "dark jacket", "clothing_lower": "denim trousers"},
    }
    ent1 = resolve_or_create_entity(repo, entity_info_1, "obs-001", active_entities)
    assert ent1.entity_id.startswith("ent-")
    assert ent1.label == "Suspect-1"
    assert ent1.associated_observation_ids == ["obs-001"]

    # Second observation of Suspect-1 with additional attribute
    entity_info_2 = {
        "entity_type": "person",
        "label": "Suspect-1",
        "attributes": {"clothing_upper": "dark jacket", "footwear": "boots"},
    }
    ent2 = resolve_or_create_entity(repo, entity_info_2, "obs-002", active_entities)

    assert ent2.entity_id == ent1.entity_id
    assert set(ent2.associated_observation_ids) == {"obs-001", "obs-002"}
    assert ent2.attributes["clothing_upper"] == "dark jacket"
    assert ent2.attributes["clothing_lower"] == "denim trousers"
    assert ent2.attributes["footwear"] == "boots"

    # Verify repository state
    saved = repo.get_entity(ent1.entity_id)
    assert saved.entity_id == ent1.entity_id
    assert set(saved.associated_observation_ids) == {"obs-001", "obs-002"}
    assert len(repo.list_entities()) == 1


@pytest.mark.parametrize("repo_type", ["in_memory", "sqlite"])
def test_distinct_entities_are_not_merged(tmp_path: Path, repo_type: str) -> None:
    """Distinct entities (different types, labels, or conflicting attributes) must NOT be merged."""
    if repo_type == "sqlite":
        repo = SqliteInvestigationRepository(tmp_path / "test.db")
    else:
        repo = InvestigationRepository()

    active_entities: dict[str, Entity] = {}

    # Person 1: Suspect-1
    ent1 = resolve_or_create_entity(
        repo,
        {"entity_type": "person", "label": "Suspect-1", "attributes": {"clothing_upper": "black hoodie"}},
        "obs-01",
        active_entities,
    )

    # Person 2: Security-Guard
    ent2 = resolve_or_create_entity(
        repo,
        {"entity_type": "person", "label": "Security-Guard", "attributes": {"clothing_upper": "high-vis vest"}},
        "obs-02",
        active_entities,
    )

    # Person 3: Same label "Suspect-1" but conflicting clothing (red jacket vs black hoodie)
    ent3 = resolve_or_create_entity(
        repo,
        {"entity_type": "person", "label": "Suspect-1", "attributes": {"clothing_upper": "red jacket"}},
        "obs-03",
        active_entities,
    )

    # Vehicle: Vehicle-1
    ent4 = resolve_or_create_entity(
        repo,
        {"entity_type": "vehicle", "label": "Vehicle-1", "attributes": {"color": "white", "vehicle_type": "sedan"}},
        "obs-04",
        active_entities,
    )

    assert ent1.entity_id != ent2.entity_id
    assert ent1.entity_id != ent3.entity_id
    assert ent1.entity_id != ent4.entity_id
    assert len(repo.list_entities()) == 4


def test_generic_labels_without_strong_overlap_are_not_merged() -> None:
    """Generic labels like 'person' or 'vehicle' with single generic attributes are not merged."""
    repo = InvestigationRepository()
    active_entities: dict[str, Entity] = {}

    ent1 = resolve_or_create_entity(
        repo,
        {"entity_type": "person", "label": "person", "attributes": {"clothing_upper": "dark jacket"}},
        "obs-01",
        active_entities,
    )

    ent2 = resolve_or_create_entity(
        repo,
        {"entity_type": "person", "label": "man", "attributes": {"clothing_upper": "dark jacket"}},
        "obs-02",
        active_entities,
    )

    # Because both labels are generic and only a single generic attribute matches,
    # conservative resolution preserves separate entities.
    assert ent1.entity_id != ent2.entity_id
    assert len(repo.list_entities()) == 2


def test_explicit_entity_id_reuse() -> None:
    """Explicit valid entity_id in entity_info is reused directly."""
    repo = InvestigationRepository()
    active_entities: dict[str, Entity] = {}

    ent1 = resolve_or_create_entity(
        repo,
        {"entity_type": "vehicle", "label": "Delivery Van", "attributes": {"color": "blue"}},
        "obs-01",
        active_entities,
    )

    ent2 = resolve_or_create_entity(
        repo,
        {"entity_id": ent1.entity_id, "entity_type": "vehicle", "label": "Delivery Van", "attributes": {"make": "Ford"}},
        "obs-02",
        active_entities,
    )

    assert ent2.entity_id == ent1.entity_id
    assert set(ent2.associated_observation_ids) == {"obs-01", "obs-02"}
    assert ent2.attributes["color"] == "blue"
    assert ent2.attributes["make"] == "Ford"
