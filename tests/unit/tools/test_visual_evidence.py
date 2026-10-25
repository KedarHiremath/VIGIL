"""Unit tests for visual evidence selection, bounding box validation, and report integration."""

import json
from pathlib import Path

import pytest
from PIL import Image

from vigil.config import config
from vigil.domain.artifact import Artifact
from vigil.domain.entity import Entity
from vigil.domain.event import Event
from vigil.domain.investigation import Investigation
from vigil.domain.media_asset import MediaAsset
from vigil.domain.observation import Observation
from vigil.domain.provenance import Provenance
from vigil.domain.report import Report
from vigil.domain.source_reference import SourceReference
from vigil.domain.visual_evidence import (
    BoundingBox,
    VisualEvidenceItem,
    validate_coordinates,
)
from vigil.models.mock import MockLLMClient
from vigil.services.exporter import ReportExporter
from vigil.storage.repository import InvestigationRepository
from vigil.tools.visual_annotator import VisualEvidenceAnnotator


def _create_sample_image(path: Path, width: int = 640, height: int = 480, color: tuple = (50, 80, 120)) -> Path:
    """Create a dummy real image for Pillow overlay testing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), color=color)
    img.save(str(path), format="JPEG")
    return path


def test_coordinate_validation() -> None:
    """Bounding box coordinates must be strictly validated for types, bounds, and ordering."""
    # Valid normalized box [x_min, y_min, x_max, y_max]
    assert validate_coordinates([0.1, 0.2, 0.5, 0.8]) == (0.1, 0.2, 0.5, 0.8)

    # Valid dict format
    assert validate_coordinates({"x_min": 0.05, "y_min": 0.1, "x_max": 0.4, "y_max": 0.9}) == (0.05, 0.1, 0.4, 0.9)

    # Normalized 0-1000 scale
    assert validate_coordinates([100, 200, 500, 800]) == (0.1, 0.2, 0.5, 0.8)

    # Invalid cases
    assert validate_coordinates([0.5, 0.2, 0.1, 0.8]) is None  # Inverted x (x_min > x_max)
    assert validate_coordinates([0.1, 0.8, 0.5, 0.2]) is None  # Inverted y (y_min > y_max)
    assert validate_coordinates([-0.1, 0.2, 0.5, 0.8]) is None  # Out of bounds (<0)
    assert validate_coordinates([0.1, 0.2, 1.2, 0.8]) is None   # Out of bounds (>1)
    assert validate_coordinates([0.1, 0.2, float("inf"), 0.8]) is None  # Non-finite
    assert validate_coordinates(["0.1", 0.2, 0.5, 0.8]) is None  # Non-numeric
    assert validate_coordinates([0.1, 0.2, 0.1001, 0.8]) is None  # Collapsed width (< 0.005)
    assert validate_coordinates([0.1, 0.2, 0.5]) is None  # Wrong length


def test_select_incident_frames_respects_limit_and_boundaries(tmp_path: Path) -> None:
    """Selection must pick top frames within configured limit, respecting media assets and diversity."""
    repo = InvestigationRepository()

    asset1 = MediaAsset(media_asset_id="cam1-feed", media_type="video", storage_uri="file:///c1.mp4")
    asset2 = MediaAsset(media_asset_id="cam2-feed", media_type="video", storage_uri="file:///c2.mp4")
    unrelated_asset = MediaAsset(media_asset_id="unrelated-cam", media_type="video", storage_uri="file:///u.mp4")
    repo.add_media_asset(asset1)
    repo.add_media_asset(asset2)
    repo.add_media_asset(unrelated_asset)

    inv = Investigation(
        investigation_id="inv-test-sel",
        title="Perimeter Test",
        objective="Determine suspect perimeter entry",
        scope_description="Perimeter cameras test scope",
        media_asset_ids=["cam1-feed", "cam2-feed"],
    )
    repo.add_investigation(inv)

    # Create 5 frames for cam1-feed at different timestamps
    frame_artifacts = []
    for i, t in enumerate([1.0, 1.2, 4.0, 8.0, 12.0]):
        art = Artifact(
            artifact_id=f"art-c1-{i}",
            artifact_type="frame",
            media_type="image",
            storage_uri=f"file:///frames/c1_{i}.jpg",
            source_reference=SourceReference(media_asset_id="cam1-feed", start_seconds=t, end_seconds=t + 0.5),
        )
        repo.add_artifact(art)
        frame_artifacts.append(art)

    # Create 1 frame for cam2-feed
    art_c2 = Artifact(
        artifact_id="art-c2-0",
        artifact_type="frame",
        media_type="image",
        storage_uri="file:///frames/c2_0.jpg",
        source_reference=SourceReference(media_asset_id="cam2-feed", start_seconds=5.0, end_seconds=5.5),
    )
    repo.add_artifact(art_c2)

    # Create 1 frame for unrelated asset (must never be selected)
    art_unrelated = Artifact(
        artifact_id="art-unrelated-0",
        artifact_type="frame",
        media_type="image",
        storage_uri="file:///frames/unrelated.jpg",
        source_reference=SourceReference(media_asset_id="unrelated-cam", start_seconds=2.0, end_seconds=2.5),
    )
    repo.add_artifact(art_unrelated)

    # Add an event for cam1 at t=4.0
    event = Event(
        event_id="evt-breach",
        event_type="perimeter_breach",
        description="Breach of south perimeter line.",
        status="confirmed",
        start_seconds=3.5,
        end_seconds=4.5,
        observation_ids=["obs-c1-2"],
    )
    repo.add_event(event)

    obs = Observation(
        observation_id="obs-c1-2",
        modality="image",
        observation_type="person_detection",
        description="Suspect crossing perimeter line",
        artifact_ids=["art-c1-2"],
        confidence=0.95,
        source_references=[SourceReference(media_asset_id="cam1-feed", start_seconds=4.0, end_seconds=4.5)],
        provenance=Provenance(producer_type="vision_model", producer_name="test", method="det"),
    )
    repo.add_observation(obs)

    annotator = VisualEvidenceAnnotator(repository=repo, storage_dir=tmp_path)

    # 1. Default limit of 3
    selected = annotator.select_incident_frames(investigation_id="inv-test-sel", max_frames=3)
    assert len(selected) == 3
    selected_ids = [a.artifact_id for a in selected]
    # art-c1-2 (confirmed event overlap at t=4.0) must be included
    assert "art-c1-2" in selected_ids
    # Unrelated media artifact must not be included
    assert "art-unrelated-0" not in selected_ids
    # Both cam1 and cam2 feeds should be represented due to diversity
    assert any(a.source_reference.media_asset_id == "cam1-feed" for a in selected)
    assert any(a.source_reference.media_asset_id == "cam2-feed" for a in selected)

    # 2. Configured limit of 2
    selected_2 = annotator.select_incident_frames(investigation_id="inv-test-sel", max_frames=2)
    assert len(selected_2) == 2


def test_select_incident_frames_handles_fewer_than_limit(tmp_path: Path) -> None:
    """If fewer frames exist than max_frames, all available are returned without error."""
    repo = InvestigationRepository()
    inv = Investigation(
        investigation_id="inv-single-frame",
        title="Single Frame Case",
        objective="Analyze single frame",
        scope_description="Single frame test scope",
        media_asset_ids=["cam-single"],
    )
    repo.add_investigation(inv)
    art = Artifact(
        artifact_id="art-single-0",
        artifact_type="frame",
        media_type="image",
        storage_uri="file:///single.jpg",
        source_reference=SourceReference(media_asset_id="cam-single", start_seconds=0.0, end_seconds=0.5),
    )
    repo.add_artifact(art)

    annotator = VisualEvidenceAnnotator(repository=repo, storage_dir=tmp_path)
    selected = annotator.select_incident_frames(investigation_id="inv-single-frame", max_frames=3)
    assert len(selected) == 1
    assert selected[0].artifact_id == "art-single-0"


def test_drawing_bounding_boxes_preserves_source_image(tmp_path: Path) -> None:
    """Bounding box overlay must generate a derivative image without modifying the source image."""
    src_file = tmp_path / "original_frame.jpg"
    _create_sample_image(src_file, width=640, height=480, color=(100, 100, 100))
    original_bytes = src_file.read_bytes()

    out_file = tmp_path / "annotated_derivative.jpg"

    repo = InvestigationRepository()
    annotator = VisualEvidenceAnnotator(repository=repo, storage_dir=tmp_path)

    boxes = [
        BoundingBox(
            x_min=0.2,
            y_min=0.3,
            x_max=0.6,
            y_max=0.8,
            label="Suspect-1",
            category="person",
            confidence=0.92,
            valid=True,
        )
    ]

    success = annotator.draw_bounding_boxes(
        source_image_path=src_file,
        output_image_path=out_file,
        boxes=boxes,
    )

    assert success is True
    assert out_file.is_file()

    # Original file is byte-for-byte identical (unmodified)
    assert src_file.read_bytes() == original_bytes

    # Derivative image is valid and has expected dimensions
    with Image.open(out_file) as ann_img:
        assert ann_img.size == (640, 480)
        assert ann_img.format == "JPEG"


def test_synthetic_and_missing_artifacts_fallback_gracefully(tmp_path: Path) -> None:
    """Synthetic or non-existent file URIs do not attempt drawing and fall back safely."""
    repo = InvestigationRepository()
    annotator = VisualEvidenceAnnotator(
        repository=repo,
        llm_client=MockLLMClient(),
        storage_dir=tmp_path,
    )

    art = Artifact(
        artifact_id="art-synthetic-01",
        artifact_type="frame",
        media_type="image",
        storage_uri="file:///storage/synthetic/non_existent_frame.jpg",
        source_reference=SourceReference(media_asset_id="cam-syn", start_seconds=1.0, end_seconds=1.5),
    )
    repo.add_artifact(art)

    item = annotator.annotate_frame(
        artifact=art,
        investigation_id="inv-syn",
        investigation_entities=[],
    )

    assert item.artifact_id == "art-synthetic-01"
    assert item.has_overlay is False
    assert item.annotated_artifact_id is None
    assert item.storage_uri == art.storage_uri


def test_visual_evidence_in_html_and_pdf_exports(tmp_path: Path) -> None:
    """HTML and PDF exports correctly render visual evidence items with tags, entities, and disclaimer."""
    # Create real dummy frame and derivative
    src_file = tmp_path / "frame_real.jpg"
    _create_sample_image(src_file, 400, 300)

    ann_file = tmp_path / "frame_annotated.jpg"
    _create_sample_image(ann_file, 400, 300, color=(30, 60, 90))

    evidence_item = VisualEvidenceItem(
        artifact_id="art-evidence-01",
        annotated_artifact_id="art-ann-01",
        storage_uri=ann_file.as_uri(),
        original_storage_uri=src_file.as_uri(),
        media_asset_id="cam-north",
        camera_id="cam-north",
        camera_label="North Gate Entry",
        timestamp_seconds=14.5,
        caption="Suspect observed breaching north perimeter fence.",
        tags=["person", "perimeter_breach", "fence"],
        resolved_entity_ids=["ent-suspect-01"],
        bounding_boxes=[
            BoundingBox(
                x_min=0.2,
                y_min=0.25,
                x_max=0.5,
                y_max=0.75,
                label="Suspect-1",
                category="person",
                confidence=0.94,
            )
        ],
        has_overlay=True,
    )

    inv = Investigation(
        investigation_id="inv-export-vis",
        title="Visual Evidence Export Test",
        objective="Verify visual evidence rendering",
        scope_description="North gate camera scope",
        media_asset_ids=["cam-north"],
    )
    report = Report(
        report_id="rep-vis-01",
        investigation_id="inv-export-vis",
        title="Forensic Deliverable With Visual Evidence",
        summary="Analysis confirmed incident with annotated visual evidence.",
        generated_by="vigil-investigator",
        evidence_frame_artifact_ids=["art-evidence-01"],
        visual_evidence=[evidence_item.model_dump()],
    )

    # 1. HTML Export
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
    )

    assert "Forensic Visual Evidence &amp; Incident Key Frames" in html_out
    assert "Suspect observed breaching north perimeter fence." in html_out
    assert "#perimeter_breach" in html_out
    assert "ent-suspect-01" in html_out
    assert "North Gate Entry" in html_out
    assert "14.5s" in html_out
    assert "Model-Generated Overlay" in html_out

    # 2. Markdown Export
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
    )

    assert "## 3. Forensic Visual Evidence & Incident Key Frames" in md_out
    assert "Suspect observed breaching north perimeter fence." in md_out
    assert "`ent-suspect-01`" in md_out
    assert "`AI OVERLAY`" in md_out

    # 3. PDF Export
    pdf_bytes = ReportExporter.export_pdf(
        investigation=inv,
        report=report,
        events=[],
        observations=[],
        assessments=[],
        coverages=[],
        artifacts=[],
        audit_logs=[],
        media_assets=[],
    )

    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
    assert len(pdf_bytes) > 2000
