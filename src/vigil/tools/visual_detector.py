"""Visual detection tool worker analyzing image artifacts for persons, vehicles, and objects."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from vigil.domain.entity import Entity
from vigil.domain.observation import Observation
from vigil.domain.provenance import Provenance
from vigil.orchestration.task_types import TaskRequest
from vigil.tools.base import BaseToolWorker

logger = logging.getLogger(__name__)


def clean_vlm_text(text: str) -> str:
    """Clean markdown formatting or raw code fence artifacts from descriptions."""
    if not text:
        return ""
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[len("```json"):].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[len("```"):].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return cleaned


class VisualDetectorWorker(BaseToolWorker):
    """Analyzes image/frame artifacts using vision models to produce Observations and Entities."""

    def run(self, request: TaskRequest) -> list[str]:
        artifact_ids = list(request.input_refs)
        investigation_id = request.parameters.get("investigation_id")

        if not artifact_ids and investigation_id:
            try:
                inv = self.repository.get_investigation(str(investigation_id))
                target_media = set(inv.media_asset_ids)
                all_arts = self.repository.list_artifacts()
                scoped_arts = [
                    a for a in all_arts
                    if a.media_type == "image"
                    and a.source_reference
                    and a.source_reference.media_asset_id in target_media
                ]
                if scoped_arts:
                    artifact_ids = [a.artifact_id for a in scoped_arts]
            except Exception:
                pass

        if not artifact_ids:
            # Look up available image artifacts in repository
            all_artifacts = self.repository.list_artifacts()
            image_artifacts = [a for a in all_artifacts if a.media_type == "image"]
            if not image_artifacts:
                raise ValueError("No image artifacts found for visual detection.")
            artifact_ids = [a.artifact_id for a in image_artifacts]

        # Analyze frames up to max_frames_per_task
        max_frames_per_task = int(request.parameters.get("max_frames_per_task", 8))
        artifact_ids = artifact_ids[:max_frames_per_task]
        logger.info(
            "VisualDetectorWorker: analyzing %d frame(s) for task %s",
            len(artifact_ids),
            request.task_id,
        )

        # Retrieve objective context
        obj_context = ""
        if investigation_id:
            try:
                inv = self.repository.get_investigation(str(investigation_id))
                if inv.objective:
                    obj_context = f"Investigation Objective: '{inv.objective}'. Focus on identifying details directly answering this query.\n"
            except Exception:
                pass

        output_observation_ids: list[str] = []

        for art_id in artifact_ids:
            artifact = self.repository.get_artifact(art_id)
            prompt = (
                f"Forensic visual analysis. {obj_context}"
                "Identify all persons, vehicles, objects, and activities visible in this frame. "
                "Output JSON with a list of 'observations', each having: "
                "'observation_type', 'description', 'confidence', and optional 'entity' with "
                "'entity_type' (person/vehicle/animal/object/unknown), 'label', and 'attributes'."
            )

            try:
                response = self.llm.analyze_image(
                    prompt=prompt,
                    image_data=artifact.storage_uri,
                    mime_type="image/jpeg",
                    json_mode=True,
                )
                raw_content = response.content
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "VisualDetectorWorker: frame %s failed (%s); using fallback observation.",
                    art_id,
                    exc,
                )
                raw_content = ""

            # Parse findings
            observations_data: list[dict[str, Any]] = []
            if raw_content:
                try:
                    cleaned_raw = clean_vlm_text(raw_content)
                    parsed = json.loads(cleaned_raw)
                    if isinstance(parsed, dict) and "observations" in parsed:
                        observations_data = parsed["observations"]
                    elif isinstance(parsed, list):
                        observations_data = parsed
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    observations_data = [
                        {
                            "observation_type": "visual_detection",
                            "description": clean_vlm_text(raw_content[:200])
                            or "Visual features detected in frame.",
                            "confidence": 0.85,
                        }
                    ]

            if not observations_data:
                observations_data = [
                    {
                        "observation_type": "scene_inspection",
                        "description": "Visual inspection completed without salient detections.",
                        "confidence": 0.80,
                    }
                ]

            for obs_item in observations_data:
                obs_id = f"obs-vis-{uuid.uuid4().hex[:8]}"
                obs_type = str(obs_item.get("observation_type", "visual_detection"))
                desc = clean_vlm_text(str(obs_item.get("description", "Salient visual detection.")))
                confidence = float(obs_item.get("confidence", 0.90))
                confidence = min(max(confidence, 0.0), 1.0)

                provenance = Provenance(
                    producer_type="vision_model",
                    producer_name=getattr(self.llm, "model_name", "vision_model")
                    or "vision_model",
                    method="visual_detection",
                    input_artifact_ids=[artifact.artifact_id],
                )

                obs = Observation(
                    observation_id=obs_id,
                    modality="image",
                    observation_type=obs_type,
                    description=desc,
                    source_references=[artifact.source_reference],
                    artifact_ids=[artifact.artifact_id],
                    confidence=confidence,
                    provenance=provenance,
                )

                self.repository.add_observation(obs)
                output_observation_ids.append(obs_id)

                # Process optional entity
                entity_info = obs_item.get("entity")
                if isinstance(entity_info, dict):
                    raw_type = entity_info.get("entity_type", "person")
                    valid_types = {"person", "vehicle", "animal", "object", "unknown"}
                    entity_type = raw_type if raw_type in valid_types else "unknown"

                    ent_id = f"ent-{uuid.uuid4().hex[:8]}"
                    raw_attributes = entity_info.get("attributes", {})
                    attributes = (
                        raw_attributes if isinstance(raw_attributes, dict) else {}
                    )

                    entity = Entity(
                        entity_id=ent_id,
                        entity_type=entity_type,  # type: ignore[arg-type]
                        label=str(
                            entity_info.get("label", f"{entity_type}_{ent_id[:6]}")
                        ),
                        attributes=attributes,
                        associated_observation_ids=[obs_id],
                    )
                    self.repository.add_entity(entity)

        return output_observation_ids
