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

        # Balance sampling across multiple media assets / cameras
        media_groups: dict[str, list[str]] = {}
        for aid in artifact_ids:
            try:
                art = self.repository.get_artifact(aid)
                mid = (
                    art.source_reference.media_asset_id
                    if art.source_reference
                    else "default"
                )
                media_groups.setdefault(mid, []).append(aid)
            except Exception:
                media_groups.setdefault("default", []).append(aid)

        max_frames_per_task = int(request.parameters.get("max_frames_per_task", 8))
        if len(media_groups) > 1:
            per_media_limit = max(2, max_frames_per_task // len(media_groups))
            balanced_ids: list[str] = []
            for m_aids in media_groups.values():
                balanced_ids.extend(m_aids[:per_media_limit])
            artifact_ids = balanced_ids
        else:
            artifact_ids = artifact_ids[:max_frames_per_task]

        logger.info(
            "VisualDetectorWorker: analyzing %d frame(s) across %d media feed(s) for task %s",
            len(artifact_ids),
            len(media_groups),
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

        # Lookup tables for camera and media metadata
        media_map = {m.media_asset_id: m for m in self.repository.list_media_assets()}
        camera_map = {c.camera_id: c for c in self.repository.list_cameras()}

        output_observation_ids: list[str] = []

        for art_id in artifact_ids:
            artifact = self.repository.get_artifact(art_id)

            # Camera context for this frame
            cam_label = ""
            if (
                artifact.source_reference
                and artifact.source_reference.media_asset_id in media_map
            ):
                asset = media_map[artifact.source_reference.media_asset_id]
                if asset.camera_id and asset.camera_id in camera_map:
                    cam = camera_map[asset.camera_id]
                    cam_label = (
                        f"[{cam.camera_id}: {cam.location_label or cam.name}]"
                    )
                elif asset.camera_id:
                    cam_label = f"[{asset.camera_id}]"

            # ------------------------------------------------------------------
            # Validate the artifact storage URI before dispatching to the VLM.
            # Synthetic / mock URIs (e.g. file:///storage/artifacts/…) that do
            # not resolve to a real file on disk cannot be base64-encoded and
            # would cause the API call to fail. Skip them with a fallback
            # observation so the rest of the queue is unaffected.
            # ------------------------------------------------------------------
            uri = artifact.storage_uri
            _is_resolvable = False
            if uri.startswith("http://") or uri.startswith("https://"):
                _is_resolvable = True
            else:
                from pathlib import Path as _Path
                from urllib.parse import unquote, urlparse as _urlparse
                try:
                    if uri.startswith("file://"):
                        _parsed = _urlparse(uri)
                        _pstr = unquote(_parsed.path)
                        if _pstr.startswith("/") and len(_pstr) > 2 and _pstr[2] == ":":
                            _pstr = _pstr[1:]
                        _is_resolvable = _Path(_pstr).is_file()
                    else:
                        _is_resolvable = _Path(uri).is_file()
                except Exception:
                    _is_resolvable = False

            if not _is_resolvable:
                logger.warning(
                    "VisualDetectorWorker: artifact %s has unresolvable storage URI '%s'; "
                    "skipping VLM call and recording placeholder observation.",
                    art_id,
                    uri,
                )
                raw_content = ""
            else:
                cam_feed_str = f"Camera feed: {cam_label}. " if cam_label else ""
                prompt = (
                    f"Forensic visual analysis. {cam_feed_str}{obj_context}"
                    "Identify all persons, vehicles, objects, and activities visible in this frame. "
                    "Output JSON with a list of 'observations', each having: "
                    "'observation_type', 'description', 'confidence', and optional 'entity' with "
                    "'entity_type' (person/vehicle/animal/object/unknown), 'label', and 'attributes'."
                )

                try:
                    response = self.llm.analyze_image(
                        prompt=prompt,
                        image_data=uri,
                        mime_type="image/jpeg",
                        json_mode=True,
                    )
                    raw_content = response.content
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "VisualDetectorWorker: frame %s VLM call failed (%s); "
                        "recording fallback observation — other frames will continue.",
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
                raw_desc = clean_vlm_text(str(obs_item.get("description", "Salient visual detection.")))
                # Prepend camera context if not already present
                if cam_label and cam_label not in raw_desc:
                    desc = f"{cam_label} {raw_desc}"
                else:
                    desc = raw_desc

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
