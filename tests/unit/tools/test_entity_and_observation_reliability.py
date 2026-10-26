"""Unit and regression tests for entity extraction, observation normalization, and report inclusion."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from vigil.domain.artifact import Artifact
from vigil.domain.entity import Entity
from vigil.domain.event import Event
from vigil.domain.investigation import Investigation
from vigil.domain.media_asset import MediaAsset
from vigil.domain.observation import Observation
from vigil.domain.provenance import Provenance
from vigil.domain.report import Report
from vigil.domain.source_reference import SourceReference
from vigil.domain.visual_evidence import VisualEvidenceItem
from vigil.models.mock import MockLLMClient
from vigil.orchestration.task_types import TaskRequest
from vigil.services.exporter import ReportExporter
from vigil.storage.repository import InvestigationRepository
from vigil.tools.visual_annotator import VisualEvidenceAnnotator
from vigil.tools.visual_detector import (
    VisualDetectorWorker,
    clean_vlm_text,
    normalize_observation_description,
    parse_vlm_detection_response,
    resolve_or_create_entity,
)


def _create_test_image(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (320, 240), color=(60, 90, 140))
    img.save(str(path), format="JPEG")
    return path


# ---------------------------------------------------------------------------
# Issue 3: Observation Normalization & Cleanup
# ---------------------------------------------------------------------------

def test_normalize_observation_description_clean_idempotence() -> None:
    """An already clean, grammatical forensic observation description must remain unchanged."""
    clean_desc = "Adult male in dark jacket and denim trousers walking eastward."
    assert normalize_observation_description(clean_desc) == clean_desc
    # Running multiple times must yield the exact same string
    assert normalize_observation_description(normalize_observation_description(clean_desc)) == clean_desc


def test_normalize_observation_description_unwraps_code_fences_and_json() -> None:
    """Raw JSON wrapped in markdown code fences must be converted to readable observation text."""
    raw_fenced = (
        "```json\n"
        "{\n"
        '  "observation_type": "person_detection",\n'
        '  "description": "Adult male in dark jacket walking toward security checkpoint.",\n'
        '  "confidence": 0.95\n'
        "}\n"
        "```"
    )
    result = normalize_observation_description(raw_fenced)
    assert result == "Adult male in dark jacket walking toward security checkpoint."


def test_normalize_observation_description_strips_model_boilerplate() -> None:
    """Common model preamble boilerplate phrases must be removed while keeping findings."""
    raw_preamble = (
        "Based on the visual evidence in the provided frame, "
        "a white 4-door sedan is parked in front of the bay door."
    )
    result = normalize_observation_description(raw_preamble)
    assert result == "A white 4-door sedan is parked in front of the bay door."

    raw_shows = "The surveillance video footage reveals an unauthorized entry through the north perimeter gate."
    result2 = normalize_observation_description(raw_shows)
    assert result2 == "An unauthorized entry through the north perimeter gate."


def test_normalize_observation_description_preserves_camera_prefix() -> None:
    """Camera context prefixes like [cam-01: Main Gate] must be preserved at the beginning."""
    raw_with_cam = (
        "[cam-01: Main Gate] In this surveillance frame, "
        "a subject approaches the electronic badge terminal."
    )
    result = normalize_observation_description(raw_with_cam)
    assert result.startswith("[cam-01: Main Gate] ")
    assert "In this surveillance frame" not in result
    assert "A subject approaches the electronic badge terminal." in result


def test_normalize_observation_description_handles_malformed_and_empty() -> None:
    """Empty, whitespace-only, or broken JSON syntax falls back safely without raising exceptions."""
    assert normalize_observation_description("") == ""
    assert normalize_observation_description("   ") == ""
    fallback = normalize_observation_description("{[]}")
    assert fallback == "Visual features observed in frame."


# ---------------------------------------------------------------------------
# Issue 2: VLM Parsing & Entity Extraction
# ---------------------------------------------------------------------------

def test_parse_vlm_detection_response_structured_json() -> None:
    """Structured JSON with observations and entities is parsed cleanly."""
    raw_json = json.dumps({
        "observations": [
            {
                "observation_type": "person_detection",
                "description": "Individual in high-visibility vest entering loading area.",
                "confidence": 0.92,
                "entity": {
                    "entity_type": "person",
                    "label": "Worker-1",
                    "attributes": {"clothing_upper": "orange vest", "role": "maintenance"},
                },
            }
        ],
        "entities": [
            {
                "entity_type": "vehicle",
                "label": "Forklift-1",
                "attributes": {"color": "yellow"},
            }
        ],
    })

    obs_data, ent_data = parse_vlm_detection_response(raw_json)
    assert len(obs_data) == 1
    assert obs_data[0]["observation_type"] == "person_detection"
    # One from observation, one top-level
    assert len(ent_data) == 2
    types = {e["entity_type"] for e in ent_data}
    assert "person" in types
    assert "vehicle" in types


def test_parse_vlm_detection_response_markdown_wrapped() -> None:
    """JSON enclosed within preamble text and markdown code fences is parsed accurately."""
    content = (
        "Here is the forensic visual analysis for the provided frame:\n\n"
        "```json\n"
        "{\n"
        '  "observations": [\n'
        '    {\n'
        '      "observation_type": "vehicle_detection",\n'
        '      "description": "Black SUV parked near emergency exit.",\n'
        '      "confidence": 0.88,\n'
        '      "entity": {\n'
        '        "entity_type": "vehicle",\n'
        '        "label": "Vehicle-9",\n'
        '        "attributes": {"color": "black", "vehicle_type": "SUV"}\n'
        '      }\n'
        '    }\n'
        '  ]\n'
        "}\n"
        "```\n"
        "Analysis complete."
    )
    obs_data, ent_data = parse_vlm_detection_response(content)
    assert len(obs_data) == 1
    assert obs_data[0]["description"] == "Black SUV parked near emergency exit."
    assert len(ent_data) == 1
    assert ent_data[0]["label"] == "Vehicle-9"


def test_parse_vlm_detection_response_free_text_narrative() -> None:
    """When a model responds with plain English narrative, observations and entities are still recovered."""
    narrative = (
        "The frame shows an adult person walking near the perimeter fence. "
        "A white vehicle is stationary in the background."
    )
    obs_data, ent_data = parse_vlm_detection_response(narrative)
    assert len(obs_data) >= 1
    assert "person" in obs_data[0]["description"].lower()
    # Should identify candidate entities from narrative mentions
    labels = [e.get("label") for e in ent_data]
    assert any("Person" in str(l) for l in labels)
    assert any("Vehicle" in str(l) for l in labels)


def test_resolve_or_create_entity_string_and_synonym_support() -> None:
    """String descriptors and category synonyms are safely mapped to valid entity types."""
    repo = InvestigationRepository()
    active: dict[str, Entity] = {}

    # String input with vehicle keyword
    ent_str = resolve_or_create_entity(repo, "White delivery truck", "obs-t1", active)
    assert ent_str.entity_type == "vehicle"
    assert ent_str.label == "White delivery truck"

    # Dict with category synonym 'human'
    ent_human = resolve_or_create_entity(
        repo,
        {"category": "human", "label": "Guard-1", "attributes": {"uniform": "blue"}},
        "obs-t2",
        active,
    )
    assert ent_human.entity_type == "person"
    assert ent_human.label == "Guard-1"


def test_visual_detector_worker_creates_and_links_entities(tmp_path: Path) -> None:
    """VisualDetectorWorker must persist normalized observations and linked entities."""
    repo = InvestigationRepository()

    img_path = tmp_path / "frame_det.jpg"
    _create_test_image(img_path)

    media = MediaAsset(media_asset_id="media-01", media_type="video", storage_uri="file:///v.mp4")
    repo.add_media_asset(media)

    art = Artifact(
        artifact_id="art-det-01",
        artifact_type="frame",
        media_type="image",
        storage_uri=img_path.as_uri(),
        source_reference=SourceReference(media_asset_id="media-01", start_seconds=5.0, end_seconds=5.5),
    )
    repo.add_artifact(art)

    inv = Investigation(
        investigation_id="inv-det-test",
        title="Detector Integration",
        objective="Identify all persons and vehicles",
        scope_description="Testing frame detection",
        media_asset_ids=["media-01"],
    )
    repo.add_investigation(inv)

    worker = VisualDetectorWorker(repository=repo, llm_client=MockLLMClient())
    request = TaskRequest(
        task_id="task-det-01",
        task_type="visual_analysis",
        input_refs=[art.artifact_id],
        parameters={"investigation_id": inv.investigation_id},
    )

    obs_ids = worker.run(request)
    assert len(obs_ids) >= 1

    # Verify observations in repository
    obs_list = repo.list_observations(obs_ids)
    for obs in obs_list:
        assert obs.artifact_ids == [art.artifact_id]
        # Description must be clean, not raw JSON
        assert not obs.description.startswith("{")
        assert not obs.description.startswith("```")

    # Verify entities in repository
    entities = repo.list_entities()
    assert len(entities) >= 1
    for ent in entities:
        # Entity must reference at least one generated observation ID
        assert any(oid in obs_ids for oid in ent.associated_observation_ids)


def test_visual_annotator_links_frame_to_resolved_entities(tmp_path: Path) -> None:
    """VisualEvidenceAnnotator connects selected incident frames to their existing resolved entities."""
    repo = InvestigationRepository()

    img_path = tmp_path / "frame_ann.jpg"
    _create_test_image(img_path)

    media = MediaAsset(media_asset_id="media-ann-01", media_type="video", storage_uri="file:///v.mp4")
    repo.add_media_asset(media)

    art = Artifact(
        artifact_id="art-ann-01",
        artifact_type="frame",
        media_type="image",
        storage_uri=img_path.as_uri(),
        source_reference=SourceReference(media_asset_id="media-ann-01", start_seconds=2.0, end_seconds=2.5),
    )
    repo.add_artifact(art)

    obs = Observation(
        observation_id="obs-ann-01",
        modality="image",
        observation_type="person_detection",
        description="Adult male walking toward warehouse door.",
        source_references=[art.source_reference],
        artifact_ids=[art.artifact_id],
        confidence=0.93,
        provenance=Provenance(producer_type="vision_model", producer_name="vlm", method="detect"),
    )
    repo.add_observation(obs)

    ent = Entity(
        entity_id="ent-person-99",
        entity_type="person",
        label="Suspect-99",
        attributes={"clothing_upper": "grey hoodie"},
        associated_observation_ids=[obs.observation_id],
    )
    repo.add_entity(ent)

    annotator = VisualEvidenceAnnotator(
        repository=repo,
        llm_client=MockLLMClient(),
        storage_dir=tmp_path / "annotated",
    )

    item = annotator.annotate_frame(
        artifact=art,
        investigation_id="inv-ann-test",
        investigation_entities=[ent],
    )

    assert item.artifact_id == art.artifact_id
    # Resolved entity must be populated from the observation linked to this frame!
    assert "ent-person-99" in item.resolved_entity_ids
    assert "person" in item.tags


# ---------------------------------------------------------------------------
# Report Exporter Integration (Markdown, HTML, PDF)
# ---------------------------------------------------------------------------

def test_report_exporter_renders_detected_entities_section(tmp_path: Path) -> None:
    """Markdown, HTML, and PDF exports must render a dedicated Detected Entities section."""
    img_path = tmp_path / "frame_rep.jpg"
    _create_test_image(img_path)

    inv = Investigation(
        investigation_id="inv-rep-test",
        title="Entity Reporting Case",
        objective="Identify all subjects on scene",
        scope_description="Surveillance report test",
        media_asset_ids=["media-rep-01"],
    )
    report = Report(
        report_id="rep-01",
        investigation_id="inv-rep-test",
        title="Formal Forensic Deliverable",
        summary="Investigation identified verified entities across examined camera feeds.",
        generated_by="lead-investigator",
        evidence_frame_artifact_ids=["art-rep-01"],
        visual_evidence=[
            {
                "artifact_id": "art-rep-01",
                "storage_uri": img_path.as_uri(),
                "original_storage_uri": img_path.as_uri(),
                "timestamp_seconds": 12.0,
                "caption": "Suspect observed walking near gate.",
                "tags": ["person", "suspect"],
                "resolved_entity_ids": ["ent-suspect-01"],
                "has_overlay": False,
            }
        ],
    )
    obs = Observation(
        observation_id="obs-rep-01",
        modality="image",
        observation_type="person_detection",
        description="Adult subject in dark outerwear walking north.",
        source_references=[SourceReference(media_asset_id="media-rep-01", start_seconds=12.0, end_seconds=12.5)],
        artifact_ids=["art-rep-01"],
        confidence=0.95,
        provenance=Provenance(producer_type="vision_model", producer_name="vlm", method="detect"),
    )
    ent = Entity(
        entity_id="ent-suspect-01",
        entity_type="person",
        label="Suspect-01",
        attributes={"clothing_upper": "dark jacket", "footwear": "boots"},
        associated_observation_ids=[obs.observation_id],
    )

    # 1. Markdown Export
    md_out = ReportExporter.export_markdown(
        investigation=inv,
        report=report,
        events=[],
        observations=[obs],
        assessments=[],
        coverages=[],
        artifacts=[],
        audit_logs=[],
        media_assets=[],
        entities=[ent],
    )
    assert "## 4. Detected Entities & Forensic Tracked Assets" in md_out
    assert "`ent-suspect-01`" in md_out
    assert "Suspect-01" in md_out
    assert "clothing_upper: dark jacket" in md_out
    assert "12.0s" in md_out

    # 2. HTML Export
    html_out = ReportExporter.export_html(
        investigation=inv,
        report=report,
        events=[],
        observations=[obs],
        assessments=[],
        coverages=[],
        artifacts=[],
        audit_logs=[],
        media_assets=[],
        entities=[ent],
    )
    assert "4. Detected Entities &amp; Tracked Forensic Assets" in html_out
    assert "ent-suspect-01" in html_out
    assert "Suspect-01" in html_out
    assert "clothing_upper: dark jacket" in html_out

    # 3. PDF Export
    pdf_bytes = ReportExporter.export_pdf(
        investigation=inv,
        report=report,
        events=[],
        observations=[obs],
        assessments=[],
        coverages=[],
        artifacts=[],
        audit_logs=[],
        media_assets=[],
        entities=[ent],
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")


def test_report_exporter_handles_genuine_empty_entities(tmp_path: Path) -> None:
    """When no entities are identified, reports display an honest, clear message rather than 'None'."""
    inv = Investigation(
        investigation_id="inv-empty-test",
        title="Empty Entity Case",
        objective="Inspect empty area",
        scope_description="Testing empty entity report",
        media_asset_ids=[],
    )
    report = Report(
        report_id="rep-empty-01",
        investigation_id="inv-empty-test",
        title="Empty Entities Report",
        summary="Analysis found no salient persons or vehicles.",
        generated_by="lead-investigator",
    )

    md_out = ReportExporter.export_markdown(
        investigation=inv,
        report=report,
        events=[],
        observations=[],
        assessments=[],
        coverages=[],
        artifacts=[],
        audit_logs=[],
        media_assets=[],
        entities=[],
    )
    assert "No entities could be reliably identified in the selected frames." in md_out

    html_out = ReportExporter.export_html(
        investigation=inv,
        report=report,
        events=[],
        observations=[],
        assessments=[],
        coverages=[],
        artifacts=[],
        audit_logs=[],
        media_assets=[],
        entities=[],
    )
    assert "No entities could be reliably identified in the selected frames." in html_out
