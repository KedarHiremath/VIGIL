"""Report-only visual evidence selection, bounding box localization, and annotation engine."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from vigil.domain.artifact import Artifact
from vigil.domain.entity import Entity
from vigil.domain.visual_evidence import (
    BoundingBox,
    VisualEvidenceItem,
    validate_coordinates,
)
from vigil.models.base import BaseLLMClient
from vigil.services.exporter import _uri_to_local_path
from vigil.storage.repository import InvestigationRepository
from vigil.tools.base import generate_sha256
from vigil.tools.visual_detector import clean_vlm_text

logger = logging.getLogger(__name__)

# Annotation cache version to invalidate stale schemas if format changes
ANNOTATION_CACHE_VERSION = "v1.0"


class VisualEvidenceAnnotator:
    """Manages report-only incident frame selection, VLM entity localization, and overlay rendering."""

    def __init__(
        self,
        repository: InvestigationRepository,
        llm_client: BaseLLMClient | None = None,
        storage_dir: Path | str | None = None,
    ) -> None:
        self.repository = repository
        self.llm = llm_client
        self.storage_dir = Path(storage_dir).resolve() if storage_dir else Path("./storage_data").resolve()
        self._memory_cache: dict[str, dict[str, Any]] = {}

    def select_incident_frames(
        self,
        investigation_id: str,
        max_frames: int = 3,
    ) -> list[Artifact]:
        """Select up to max_frames informative incident-relevant frames using existing evidence and metadata.

        No new video extraction is performed; only existing extracted frame artifacts are evaluated.
        """
        try:
            inv = self.repository.get_investigation(investigation_id)
            target_media = set(inv.media_asset_ids)
            objective = (inv.objective or "").lower()
        except Exception:
            target_media = set()
            objective = ""

        all_artifacts = self.repository.list_artifacts()
        # Find candidate image/frame artifacts belonging to this investigation's media feeds
        candidates: list[Artifact] = []
        for art in all_artifacts:
            if art.media_type != "image" or art.artifact_type not in {"frame", "crop"}:
                continue
            if art.source_reference and target_media:
                if art.source_reference.media_asset_id in target_media:
                    candidates.append(art)
            elif not target_media:
                candidates.append(art)

        if not candidates:
            return []

        # Gather investigation context (events and observations)
        state = self.repository.get_state(investigation_id)
        scoped_event_ids = set(state.event_ids) if state else set()
        scoped_obs_ids = set(state.observation_ids) if state else set()

        events = self.repository.list_events(list(scoped_event_ids)) if scoped_event_ids else self.repository.list_events()
        observations = self.repository.list_observations(list(scoped_obs_ids)) if scoped_obs_ids else self.repository.list_observations()

        # Index observations by artifact_id
        obs_by_art: dict[str, list[Any]] = {}
        for obs in observations:
            for aid in obs.artifact_ids:
                obs_by_art.setdefault(aid, []).append(obs)

        # Objective keywords for relevance matching
        obj_words = {
            w for w in objective.replace(",", " ").replace(".", " ").split()
            if len(w) > 3 and w not in {"what", "when", "where", "identify", "determine", "timeline", "forensic"}
        }

        # Score candidate frames
        scored_candidates: list[tuple[float, Artifact]] = []
        for art in candidates:
            score = 5.0  # Base score
            sr = art.source_reference
            frame_t = sr.start_seconds if sr else None

            # 1. Event overlap scoring
            for evt in events:
                evt_has_art = False
                for oid in evt.observation_ids:
                    matching_obs = [o for o in observations if o.observation_id == oid]
                    if any(art.artifact_id in o.artifact_ids for o in matching_obs):
                        evt_has_art = True
                        break

                t_overlap = False
                if frame_t is not None and evt.start_seconds is not None and evt.end_seconds is not None:
                    if evt.start_seconds - 0.5 <= frame_t <= evt.end_seconds + 0.5:
                        t_overlap = True

                if evt_has_art or t_overlap:
                    if evt.status == "confirmed":
                        score += 50.0
                    elif evt.status in {"proposed", "under_review"}:
                        score += 30.0
                    else:
                        score += 10.0

            # 2. Observation quality scoring
            linked_obs = obs_by_art.get(art.artifact_id, [])
            for obs in linked_obs:
                conf = obs.confidence if obs.confidence is not None else 0.8
                score += conf * 20.0
                if obs.observation_type in {"person_detection", "vehicle_detection", "visual_detection"}:
                    score += 15.0
                desc_lower = obs.description.lower()
                if any(kw in desc_lower for kw in obj_words):
                    score += 12.0

            scored_candidates.append((score, art))

        # Sort descending by score
        scored_candidates.sort(key=lambda pair: pair[0], reverse=True)

        # Enforce diversity across camera feeds and temporal spacing (>= 1.5s apart on same feed)
        selected: list[Artifact] = []
        for _, art in scored_candidates:
            if len(selected) >= max_frames:
                break

            art_media = art.source_reference.media_asset_id if art.source_reference else "default"
            art_t = art.source_reference.start_seconds if art.source_reference else 0.0

            # Check spacing with already selected frames from the same media asset
            too_close = False
            for s in selected:
                s_media = s.source_reference.media_asset_id if s.source_reference else "default"
                s_t = s.source_reference.start_seconds if s.source_reference else 0.0
                if art_media == s_media and art_t is not None and s_t is not None:
                    if abs(art_t - s_t) < 1.5:
                        too_close = True
                        break

            if not too_close:
                selected.append(art)

        # If diversity constraint left fewer than max_frames, fill with remaining highest scored
        if len(selected) < max_frames:
            selected_ids = {a.artifact_id for a in selected}
            for _, art in scored_candidates:
                if len(selected) >= max_frames:
                    break
                if art.artifact_id not in selected_ids:
                    selected.append(art)
                    selected_ids.add(art.artifact_id)

        logger.info(
            "VisualEvidenceAnnotator: selected %d incident frame(s) for investigation %s",
            len(selected),
            investigation_id,
        )
        return selected[:max_frames]

    def _get_cache_key(self, artifact: Artifact) -> str:
        ident = artifact.sha256 or artifact.artifact_id
        model_name = getattr(self.llm, "model_name", "vlm") if self.llm else "vlm"
        return f"{ident}:{model_name}:{ANNOTATION_CACHE_VERSION}"

    def draw_bounding_boxes(
        self,
        source_image_path: Path,
        output_image_path: Path,
        boxes: list[BoundingBox],
    ) -> bool:
        """Draw bounding boxes and concise labels on a copy of the source image.

        Never modifies or overwrites the source image.
        """
        if not source_image_path.is_file():
            return False

        valid_boxes = [b for b in boxes if b.valid]
        if not valid_boxes:
            return False

        try:
            with Image.open(source_image_path) as src_img:
                img = src_img.convert("RGB")

            width, height = img.size
            draw = ImageDraw.Draw(img)

            # Palette for distinct entity categories
            palette = {
                "person": "#38bdf8",   # Sky blue
                "vehicle": "#fbbf24",  # Amber
                "object": "#34d399",   # Emerald green
                "unknown": "#f87171",  # Red
            }

            for box in valid_boxes:
                color = palette.get(box.category.lower(), "#38bdf8")

                px_min = max(0, min(width - 1, int(box.x_min * width)))
                py_min = max(0, min(height - 1, int(box.y_min * height)))
                px_max = max(0, min(width, int(box.x_max * width)))
                py_max = max(0, min(height, int(box.y_max * height)))

                # Draw outer bounding rectangle
                draw.rectangle([px_min, py_min, px_max, py_max], outline=color, width=3)

                # Draw concise label badge
                conf_str = f" {box.confidence:.0%}" if box.confidence else ""
                label_text = f"{box.label}{conf_str}"

                # Calculate badge bounding box
                font = ImageFont.load_default()
                text_bbox = draw.textbbox((px_min + 3, py_min - 16), label_text, font=font)
                badge_bg = [
                    max(0, text_bbox[0] - 2),
                    max(0, text_bbox[1] - 2),
                    min(width, text_bbox[2] + 4),
                    min(height, text_bbox[3] + 2),
                ]
                draw.rectangle(badge_bg, fill="#0f172a")
                draw.text((badge_bg[0] + 3, badge_bg[1] + 1), label_text, fill=color, font=font)

            output_image_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(str(output_image_path), format="JPEG", quality=90)
            return True
        except Exception as exc:
            logger.warning("VisualEvidenceAnnotator: Failed to render bounding boxes: %s", exc)
            return False

    def annotate_frame(
        self,
        artifact: Artifact,
        investigation_id: str,
        investigation_entities: list[Entity],
    ) -> VisualEvidenceItem:
        """Analyze a selected frame, extract tags and bounding boxes, and generate a report derivative."""
        cache_key = self._get_cache_key(artifact)
        cached = self._memory_cache.get(cache_key)

        caption = "Salient visual evidence recorded for incident timeline."
        tags: list[str] = ["incident_evidence", "visual_frame"]
        raw_detections: list[dict[str, Any]] = []

        local_path = _uri_to_local_path(artifact.storage_uri)

        if cached:
            caption = cached.get("caption", caption)
            tags = cached.get("tags", tags)
            raw_detections = cached.get("detections", [])
        elif self.llm is not None and local_path is not None and local_path.is_file():
            prompt = (
                "Forensic object localization and tagging. "
                "Detect key entities (person, vehicle, object) visible in this frame relevant to an investigation. "
                "Output valid JSON in this exact structure: "
                "{"
                '  "caption": "Concise scene description", '
                '  "tags": ["tag1", "tag2"], '
                '  "detections": ['
                "    {"
                '      "category": "person | vehicle | object", '
                '      "label": "Suspect-1 | Vehicle-1", '
                '      "box_2d": [x_min, y_min, x_max, y_max], '
                '      "attributes": {"color": "...", "clothing_upper": "..."}, '
                '      "confidence": 0.95'
                "    }"
                "  ]"
                "} "
                "Normalized coordinates must be floats between 0.0 and 1.0 in [x_min, y_min, x_max, y_max] order."
            )
            try:
                response = self.llm.analyze_image(
                    prompt=prompt,
                    image_data=artifact.storage_uri,
                    mime_type="image/jpeg",
                    json_mode=True,
                )
                if response and response.content:
                    cleaned = clean_vlm_text(response.content)
                    parsed = json.loads(cleaned)
                    if isinstance(parsed, dict):
                        caption = str(parsed.get("caption") or caption)
                        raw_tags = parsed.get("tags", [])
                        if isinstance(raw_tags, list):
                            tags = [str(t).strip() for t in raw_tags if str(t).strip()]
                        raw_detections = parsed.get("detections", [])
                        if not isinstance(raw_detections, list):
                            raw_detections = []

                # Cache valid raw output
                self._memory_cache[cache_key] = {
                    "caption": caption,
                    "tags": tags,
                    "detections": raw_detections,
                }
            except Exception as exc:
                logger.warning(
                    "VisualEvidenceAnnotator: VLM localization failed for artifact %s: %s; using unannotated evidence fallback.",
                    artifact.artifact_id,
                    exc,
                )

        # Build and validate BoundingBox models
        validated_boxes: list[BoundingBox] = []
        resolved_entity_ids: list[str] = []

        # Index known investigation entities by label for resolution linking
        entity_by_label: dict[str, Entity] = {}
        for ent in investigation_entities:
            if ent.label:
                entity_by_label[ent.label.strip().lower()] = ent

        for det in raw_detections:
            if not isinstance(det, dict):
                continue

            raw_box = det.get("box_2d", det.get("bbox", det.get("bounding_box")))
            valid_coords = validate_coordinates(raw_box)
            if not valid_coords:
                continue

            label = str(det.get("label", "Object")).strip() or "Object"
            category = str(det.get("category", "object")).strip().lower()
            confidence = det.get("confidence")
            if isinstance(confidence, (int, float)):
                confidence = max(0.0, min(1.0, float(confidence)))
            else:
                confidence = None

            # Attempt entity resolution linking
            matched_ent_id: str | None = None
            if label.lower() in entity_by_label:
                matched_ent_id = entity_by_label[label.lower()].entity_id
                if matched_ent_id not in resolved_entity_ids:
                    resolved_entity_ids.append(matched_ent_id)

            raw_attr = det.get("attributes", {})
            attr = dict(raw_attr) if isinstance(raw_attr, dict) else {}

            bbox = BoundingBox(
                x_min=valid_coords[0],
                y_min=valid_coords[1],
                x_max=valid_coords[2],
                y_max=valid_coords[3],
                label=label,
                category=category,
                confidence=confidence,
                entity_id=matched_ent_id,
                attributes=attr,
                valid=True,
            )
            validated_boxes.append(bbox)

        # Draw derivative annotated image if local file exists and boxes are valid
        annotated_art_id: str | None = None
        has_overlay = False
        display_uri = artifact.storage_uri

        if local_path and local_path.is_file() and validated_boxes:
            annotated_dir = self.storage_dir / "annotated_evidence" / investigation_id
            annotated_filename = f"{artifact.artifact_id}_annotated.jpg"
            annotated_path = annotated_dir / annotated_filename

            drawn = self.draw_bounding_boxes(
                source_image_path=local_path,
                output_image_path=annotated_path,
                boxes=validated_boxes,
            )

            if drawn and annotated_path.is_file():
                has_overlay = True
                display_uri = annotated_path.as_uri()
                annotated_art_id = f"art-ann-{uuid.uuid4().hex[:8]}"
                derivative_art = Artifact(
                    artifact_id=annotated_art_id,
                    artifact_type="derived_media",
                    media_type="image",
                    storage_uri=display_uri,
                    source_reference=artifact.source_reference,
                    sha256=generate_sha256(annotated_path.read_bytes()),
                )
                self.repository.add_artifact(derivative_art)

        # Extract camera and timeline context
        sr = artifact.source_reference
        media_id = sr.media_asset_id if sr else None
        timestamp_s = sr.start_seconds if sr else None

        camera_id = None
        camera_label = None
        if media_id:
            try:
                media_asset = self.repository.get_media_asset(media_id)
                camera_id = media_asset.camera_id
                if camera_id:
                    cam = self.repository.get_camera(camera_id)
                    camera_label = cam.location_label or cam.name
            except Exception:
                pass

        return VisualEvidenceItem(
            artifact_id=artifact.artifact_id,
            annotated_artifact_id=annotated_art_id,
            storage_uri=display_uri,
            original_storage_uri=artifact.storage_uri,
            media_asset_id=media_id,
            camera_id=camera_id,
            camera_label=camera_label,
            timestamp_seconds=timestamp_s,
            caption=caption,
            tags=tags,
            resolved_entity_ids=resolved_entity_ids,
            bounding_boxes=validated_boxes,
            has_overlay=has_overlay,
        )

    def prepare_visual_evidence(
        self,
        investigation_id: str,
        max_frames: int = 3,
    ) -> list[VisualEvidenceItem]:
        """High-level pipeline: Select up to max_frames incident frames and annotate them."""
        selected_artifacts = self.select_incident_frames(
            investigation_id=investigation_id,
            max_frames=max_frames,
        )
        if not selected_artifacts:
            return []

        all_entities = self.repository.list_entities()
        items: list[VisualEvidenceItem] = []
        for art in selected_artifacts:
            item = self.annotate_frame(
                artifact=art,
                investigation_id=investigation_id,
                investigation_entities=all_entities,
            )
            items.append(item)

        return items
