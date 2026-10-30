"""Unit tests for EventCorrelatorWorker major evidence analysis and response parsing."""

from __future__ import annotations

from unittest.mock import MagicMock

from vigil.domain.media_asset import MediaAsset
from vigil.domain.observation import Observation
from vigil.domain.provenance import Provenance
from vigil.domain.source_reference import SourceReference
from vigil.orchestration.task_types import TaskRequest
from vigil.storage.repository import InvestigationRepository
from vigil.tools.event_correlator import (
    EventCorrelatorWorker,
    parse_correlator_response,
)


def test_parse_correlator_response_code_fences_and_preamble() -> None:
    """Verify parse_correlator_response strips markdown fences and extracts valid events."""
    raw = """
    Here is the forensic correlation analysis:
    ```json
    {
      "events": [
        {
          "event_type": "perimeter_breach",
          "description": "Subject climbing security fence near north gate.",
          "observation_ids": ["obs-1", "obs-2"]
        }
      ],
      "links": [
        {
          "from_event_index": 0,
          "to_event_index": 1,
          "relationship_type": "before",
          "rationale": "Chronological occurrence."
        }
      ]
    }
    ```
    Analysis concluded.
    """
    events, links = parse_correlator_response(raw)
    assert len(events) == 1
    assert events[0]["event_type"] == "perimeter_breach"
    assert "climbing security fence" in events[0]["description"]
    assert events[0]["observation_ids"] == ["obs-1", "obs-2"]
    assert len(links) == 1


def test_event_correlator_creates_discrete_major_evidence_clusters() -> None:
    """Verify fallback clustering segments timeline into discrete events with descriptive summaries."""
    repo = InvestigationRepository()

    # Create media asset
    asset = MediaAsset(
        media_asset_id="media-cam-1",
        media_type="video",
        storage_uri="file:///test.mp4",
        camera_id="cam-north",
        duration_seconds=100.0,
    )
    repo.add_media_asset(asset)

    prov = Provenance(producer_type="vision_model", producer_name="vlm-1", method="visual_analysis")

    # Cluster 1: Person activity at 5.0s - 10.0s
    obs1 = Observation(
        observation_id="obs-cluster1-1",
        modality="video",
        observation_type="person_detection",
        description="[cam-north] Person in dark clothing walking toward entrance.",
        confidence=0.92,
        source_references=[SourceReference(media_asset_id="media-cam-1", start_seconds=5.0, end_seconds=7.0)],
        provenance=prov,
    )
    obs2 = Observation(
        observation_id="obs-cluster1-2",
        modality="video",
        observation_type="person_detection",
        description="[cam-north] Person inspecting entrance security door.",
        confidence=0.88,
        source_references=[SourceReference(media_asset_id="media-cam-1", start_seconds=7.5, end_seconds=10.0)],
        provenance=prov,
    )

    # Cluster 2: Vehicle activity at 50.0s - 55.0s (40s time gap > 8.0s)
    obs3 = Observation(
        observation_id="obs-cluster2-1",
        modality="video",
        observation_type="vehicle_detection",
        description="[cam-north] White delivery van pulling up to loading bay.",
        confidence=0.95,
        source_references=[SourceReference(media_asset_id="media-cam-1", start_seconds=50.0, end_seconds=52.5)],
        provenance=prov,
    )
    obs4 = Observation(
        observation_id="obs-cluster2-2",
        modality="video",
        observation_type="vehicle_detection",
        description="[cam-north] Delivery van stopping with hazard lights activated.",
        confidence=0.90,
        source_references=[SourceReference(media_asset_id="media-cam-1", start_seconds=53.0, end_seconds=55.0)],
        provenance=prov,
    )

    for o in [obs1, obs2, obs3, obs4]:
        repo.add_observation(o)

    # Mock LLM that returns invalid text to test robust forensic clustering fallback
    failing_llm = MagicMock()
    failing_llm.generate_text.side_effect = RuntimeError("API unavailable")

    worker = EventCorrelatorWorker(repository=repo, llm_client=failing_llm)
    req = TaskRequest(
        task_id="task-corr-cluster",
        task_type="event_correlation",
        input_refs=["obs-cluster1-1", "obs-cluster1-2", "obs-cluster2-1", "obs-cluster2-2"],
        parameters={},
    )

    event_ids = worker.run(req)
    assert len(event_ids) == 2  # Must NOT lump everything into 1 single event

    ev1 = repo.get_event(event_ids[0])
    ev2 = repo.get_event(event_ids[1])

    # Event 1 checks
    assert ev1.event_type == "person_activity"
    assert "Person in dark clothing" in ev1.description
    assert ev1.start_seconds == 5.0
    assert ev1.end_seconds == 10.0
    assert set(ev1.observation_ids) == {"obs-cluster1-1", "obs-cluster1-2"}
    assert "Correlated occurrence supported by visual and/or acoustic observations." not in ev1.description

    # Event 2 checks
    assert ev2.event_type == "vehicle_movement"
    assert "White delivery van" in ev2.description
    assert ev2.start_seconds == 50.0
    assert ev2.end_seconds == 55.0
    assert set(ev2.observation_ids) == {"obs-cluster2-1", "obs-cluster2-2"}

    # Links check
    links = repo.list_event_links()
    assert len(links) >= 1
    assert links[0].from_event_id == ev1.event_id
    assert links[0].to_event_id == ev2.event_id
    assert links[0].relationship_type == "before"
