"""Tests for VIGIL evidence and interpretation schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from vigil.domain.entity import Entity
from vigil.domain.event import Event
from vigil.domain.event_link import EventLink
from vigil.domain.evidence_assessment import EvidenceAssessment
from vigil.domain.observation import Observation
from vigil.domain.provenance import Provenance
from vigil.domain.source_reference import SourceReference


def make_provenance() -> Provenance:
    """Create valid provenance for test observations."""
    return Provenance(
        producer_type="vision_model",
        producer_name="test-vision-model",
        method="frame_description",
    )


def make_observation(
    observation_id: str = "obs_001",
) -> Observation:
    """Create a valid test observation."""
    return Observation(
        observation_id=observation_id,
        modality="video",
        observation_type="person_detection",
        description="A person appears in the frame.",
        source_references=[
            SourceReference(
                media_asset_id="media_001",
                start_seconds=10.0,
                end_seconds=12.0,
            )
        ],
        provenance=make_provenance(),
    )


def test_observation_requires_source_reference() -> None:
    with pytest.raises(ValidationError):
        Observation(
            observation_id="obs_001",
            modality="video",
            observation_type="person_detection",
            description="A person appears.",
            source_references=[],
            provenance=make_provenance(),
        )


# def test_observation_rejects_invalid_confidence() -> None:
#     with pytest.raises(ValidationError):
#         make_observation().model_copy(
#             update={"confidence": 1.5}
#         )
def test_observation_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        Observation(
            observation_id="obs_001",
            modality="video",
            observation_type="person_detection",
            description="A person appears.",
            source_references=[
                SourceReference(
                    media_asset_id="media_001",
                    start_seconds=10.0,
                    end_seconds=12.0,
                )
            ],
            provenance=make_provenance(),
            confidence=1.5,
        )


def test_provenance_rejects_duplicate_artifact_ids() -> None:
    with pytest.raises(ValidationError):
        Provenance(
            producer_type="vision_model",
            producer_name="test-model",
            method="detection",
            input_artifact_ids=["artifact_001", "artifact_001"],
        )


def test_entity_requires_observation_reference() -> None:
    with pytest.raises(ValidationError):
        Entity(
            entity_id="entity_001",
            entity_type="person",
            associated_observation_ids=[],
        )


def test_entity_accepts_valid_references() -> None:
    entity = Entity(
        entity_id="entity_001",
        entity_type="person",
        associated_observation_ids=["obs_001", "obs_002"],
        attributes={"clothing_color": "red"},
    )

    assert entity.entity_type == "person"


def test_event_requires_supporting_observations() -> None:
    with pytest.raises(ValidationError):
        Event(
            event_id="event_001",
            event_type="person_entry",
            description="A person entered the area.",
            observation_ids=[],
        )


def test_event_rejects_reversed_timestamps() -> None:
    with pytest.raises(ValidationError):
        Event(
            event_id="event_001",
            event_type="person_entry",
            description="A person entered the area.",
            observation_ids=["obs_001"],
            start_time=datetime(2026, 10, 14, 12, tzinfo=UTC),
            end_time=datetime(2026, 10, 14, 11, tzinfo=UTC),
        )


def test_event_link_rejects_self_link() -> None:
    with pytest.raises(ValidationError):
        EventLink(
            event_link_id="link_001",
            from_event_id="event_001",
            to_event_id="event_001",
            relationship_type="related_to",
            rationale="Test relationship.",
        )


def test_event_link_accepts_distinct_events() -> None:
    link = EventLink(
        event_link_id="link_001",
        from_event_id="event_001",
        to_event_id="event_002",
        relationship_type="before",
        rationale="The first event preceded the second.",
    )

    assert link.relationship_type == "before"


def test_evidence_assessment_accepts_valid_target() -> None:
    assessment = EvidenceAssessment(
        assessment_id="assessment_001",
        target_type="observation",
        target_id="obs_001",
        assessment_type="evidence_quality",
        rating="moderate",
        rationale="The observation is clear but requires corroboration.",
        assessed_by="reviewer_001",
    )

    assert assessment.target_id == "obs_001"


def test_evidence_assessment_rejects_blank_rationale() -> None:
    with pytest.raises(ValidationError):
        EvidenceAssessment(
            assessment_id="assessment_001",
            target_type="event",
            target_id="event_001",
            assessment_type="support_level",
            rating="high",
            rationale=" ",
            assessed_by="reviewer_001",
        )


def test_observation_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Observation(
            observation_id="obs_001",
            modality="video",
            observation_type="person_detection",
            description="A person appears.",
            source_references=[
                SourceReference(
                    media_asset_id="media_001",
                    start_seconds=10.0,
                    end_seconds=12.0,
                )
            ],
            provenance=make_provenance(),
            unknown_field="not_allowed",
        )

def test_observation_identifier_uses_shared_contract() -> None:
    observation = Observation(
        observation_id="  obs-001  ",
        modality="video",
        observation_type="person_detection",
        description="A person entered the frame.",
        source_references=[
            SourceReference(
                media_asset_id="media-001",
                start_seconds=1.0,
                end_seconds=2.0,
            )
        ],
        provenance=Provenance(
            producer_type="vision_model",
            producer_name="detector",
            method="person_detection",
        ),
    )

    assert observation.observation_id == "obs-001"


def test_provenance_rejects_duplicate_references_after_normalization() -> None:
    with pytest.raises(ValidationError):
        Provenance(
            producer_type="vision_model",
            producer_name="detector",
            method="person_detection",
            input_artifact_ids=["artifact-001", " artifact-001 "],
        )


def test_observation_rejects_non_finite_confidence() -> None:
    with pytest.raises(ValidationError):
        Observation(
            observation_id="obs-001",
            modality="video",
            observation_type="person_detection",
            description="A person entered the frame.",
            source_references=[
                SourceReference(
                    media_asset_id="media-001",
                    start_seconds=1.0,
                    end_seconds=2.0,
                )
            ],
            confidence=float("nan"),
            provenance=Provenance(
                producer_type="vision_model",
                producer_name="detector",
                method="person_detection",
            ),
        )


def test_entity_rejects_duplicate_observation_ids_after_normalization() -> None:
    with pytest.raises(ValidationError):
        Entity(
            entity_id="entity-001",
            entity_type="person",
            associated_observation_ids=["obs-001", " obs-001 "],
        )


def test_event_rejects_naive_start_time() -> None:
    with pytest.raises(ValidationError):
        Event(
            event_id="event-001",
            event_type="entry",
            description="A person entered the area.",
            observation_ids=["obs-001"],
            start_time=datetime(2026, 10, 15, 9, 0),
        )


def test_event_link_normalizes_ids_before_self_link_check() -> None:
    with pytest.raises(ValidationError):
        EventLink(
            event_link_id="link-001",
            from_event_id="event-001",
            to_event_id=" event-001 ",
            relationship_type="related_to",
            rationale="Testing normalized identifiers.",
        )


def test_event_link_rejects_non_finite_confidence() -> None:
    with pytest.raises(ValidationError):
        EventLink(
            event_link_id="link-001",
            from_event_id="event-001",
            to_event_id="event-002",
            relationship_type="related_to",
            rationale="Possible relationship.",
            confidence=float("inf"),
        )


def test_evidence_assessment_normalizes_target_id() -> None:
    assessment = EvidenceAssessment(
        assessment_id="assessment-001",
        target_type="observation",
        target_id=" obs-001 ",
        assessment_type="evidence_quality",
        rating="high",
        rationale="The source is clear.",
        assessed_by="reviewer-001",
    )

    assert assessment.target_id == "obs-001"