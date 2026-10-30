"""Visual detection tool worker analyzing image artifacts for persons, vehicles, and objects."""

from __future__ import annotations

import json
import logging
import math
import re
import uuid
from typing import Any

from vigil.domain.artifact import Artifact
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
    if "```" in cleaned:
        fence_match = re.search(r"```(?:json|markdown)?\s*([\s\S]*?)\s*```", cleaned)
        if fence_match:
            return fence_match.group(1).strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[len("```json"):].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned[len("```"):].strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    return cleaned


def parse_confidence(val: Any, default: float = 0.90) -> float:
    """Safely parse qualitative, string, or numeric confidence values into a float in [0.0, 1.0]."""
    if val is None:
        return default
    if isinstance(val, (int, float)):
        if math.isfinite(val):
            return min(max(float(val), 0.0), 1.0)
        return default
    if isinstance(val, str):
        v = val.strip().lower().rstrip("%")
        if v in {"high", "very high", "very_high", "strong"}:
            return 0.90
        if v in {"medium", "moderate"}:
            return 0.75
        if v in {"low", "very low", "very_low", "weak"}:
            return 0.50
        try:
            num = float(v)
            if math.isfinite(num):
                if num > 1.0 and num <= 100.0:
                    num = num / 100.0
                return min(max(num, 0.0), 1.0)
        except ValueError:
            pass
    return default


def normalize_observation_description(text: str) -> str:
    """Normalize raw model outputs into a clean, concise, grammatical forensic description.

    Idempotent: An already-clean human-readable description remains completely unchanged.
    Removes raw JSON wrappers, markdown code fences, unescaped characters, and model boilerplate.
    Preserves camera context prefix, timestamps, and verifiable evidence.
    """
    if not text or not str(text).strip():
        return ""
    cleaned = str(text).strip()

    # Extract camera context prefix if present, e.g. "[cam-north: North Gate] "
    cam_prefix = ""
    cam_match = re.match(r"^(\[[^\]]+\])\s*", cleaned)
    if cam_match:
        cam_prefix = cam_match.group(1) + " "
        cleaned = cleaned[cam_match.end():].strip()

    # Unwrap markdown fences
    if "```" in cleaned:
        cleaned = clean_vlm_text(cleaned)

    # If the text is JSON or contains JSON structure, parse it
    if (cleaned.startswith("{") and cleaned.endswith("}")) or (cleaned.startswith("[") and cleaned.endswith("]")) or ("{" in cleaned and "}" in cleaned):
        try:
            json_str = cleaned
            if not (cleaned.startswith("{") or cleaned.startswith("[")):
                start_obj = cleaned.find("{")
                start_arr = cleaned.find("[")
                start_candidates = [idx for idx in (start_obj, start_arr) if idx != -1]
                if start_candidates:
                    start_idx = min(start_candidates)
                    end_idx = max(cleaned.rfind("}"), cleaned.rfind("]"))
                    if end_idx > start_idx:
                        json_str = cleaned[start_idx : end_idx + 1]

            parsed = json.loads(json_str)
            if isinstance(parsed, dict):
                if parsed.get("description"):
                    cleaned = str(parsed["description"])
                elif parsed.get("observations") and isinstance(parsed["observations"], list):
                    items = []
                    for itm in parsed["observations"]:
                        if isinstance(itm, dict):
                            desc_part = itm.get("description") or itm.get("finding") or itm.get("label")
                            if desc_part:
                                items.append(str(desc_part).strip())
                        elif isinstance(itm, str):
                            items.append(itm.strip())
                    if items:
                        cleaned = " ".join(items)
                elif parsed.get("scene") or parsed.get("summary"):
                    cleaned = str(parsed.get("scene") or parsed.get("summary"))
                elif parsed.get("label") or parsed.get("finding"):
                    cleaned = str(parsed.get("label") or parsed.get("finding"))
                else:
                    parts = [f"{k}: {v}" for k, v in parsed.items() if v and isinstance(v, (str, int, float))]
                    if parts:
                        cleaned = "; ".join(parts)
            elif isinstance(parsed, list):
                items = []
                for itm in parsed:
                    if isinstance(itm, dict):
                        d = itm.get("description") or itm.get("label")
                        if d:
                            items.append(str(d).strip())
                    elif isinstance(itm, str):
                        items.append(itm.strip())
                if items:
                    cleaned = " ".join(items)
        except Exception:
            pass

    # Clean escaped characters
    cleaned = cleaned.replace('\\"', '"').replace('\\n', ' ').replace('\\r', '')

    # Remove AI / VLM boilerplate phrases (case-insensitive)
    boilerplate_patterns = [
        r"^(?:based on (?:the )?(?:visual|image|frame|surveillance|provided)[^,:\.\n]*[,:\.\n]\s*)",
        r"^(?:in this (?:surveillance )?(?:frame|image|scene|video)[^,:\.\n]*[,:\.\n]\s*)",
        r"^(?:the (?:provided )?(?:surveillance )?(?:video )?(?:footage|image|frame|scene) (?:shows|depicts|displays|reveals|contains)\s*)",
        r"^(?:here is the (?:visual |forensic )?analysis[^,:\.\n]*[,:\.\n]\s*)",
        r"^(?:we can observe that\s*)",
        r"^(?:it appears that\s*)",
    ]
    for pat in boilerplate_patterns:
        cleaned = re.sub(pat, "", cleaned, flags=re.IGNORECASE).strip()

    # Clean redundant JSON / syntax remnants
    cleaned = re.sub(r"[\{\}\[\]]", "", cleaned)
    cleaned = re.sub(r'^\s*["\']\s*', "", cleaned)
    cleaned = re.sub(r'\s*["\']\s*$', "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Capitalize the first character
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]

    # Fallback if text is empty or meaningless
    if not cleaned or len(cleaned) < 3 or set(cleaned).issubset(set(".,;:-_ '\"")):
        cleaned = "Visual features observed in frame."

    return f"{cam_prefix}{cleaned}"


def parse_vlm_detection_response(raw_content: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse VLM output into structured observation items and candidate entity descriptors.

    Robustly handles markdown fences, embedded JSON, top-level entities, and free-text narratives.
    """
    if not raw_content or not raw_content.strip():
        return [], []

    cleaned = clean_vlm_text(raw_content)
    parsed: Any = None

    try:
        parsed = json.loads(cleaned)
    except Exception:
        start_obj = cleaned.find("{")
        start_arr = cleaned.find("[")
        start_candidates = [idx for idx in (start_obj, start_arr) if idx != -1]
        if start_candidates:
            start_idx = min(start_candidates)
            end_idx = max(cleaned.rfind("}"), cleaned.rfind("]"))
            if end_idx > start_idx:
                try:
                    parsed = json.loads(cleaned[start_idx : end_idx + 1])
                except Exception:
                    parsed = None

    observations_data: list[dict[str, Any]] = []
    entities_data: list[dict[str, Any]] = []

    if isinstance(parsed, dict):
        if "observations" in parsed:
            raw_obs = parsed["observations"]
            if isinstance(raw_obs, list):
                observations_data = [item for item in raw_obs if isinstance(item, dict)]
            elif isinstance(raw_obs, dict):
                observations_data = [raw_obs]
        elif "findings" in parsed and isinstance(parsed["findings"], list):
            observations_data = [item for item in parsed["findings"] if isinstance(item, dict)]
        elif "detections" in parsed and isinstance(parsed["detections"], list):
            observations_data = [item for item in parsed["detections"] if isinstance(item, dict)]
        elif "description" in parsed:
            observations_data = [parsed]

        top_entities = parsed.get("entities")
        if isinstance(top_entities, list):
            for e in top_entities:
                if isinstance(e, dict):
                    entities_data.append(e)
                elif isinstance(e, str) and e.strip():
                    entities_data.append({"label": e.strip(), "entity_type": "object"})
        elif isinstance(parsed.get("entity"), (dict, str)):
            e = parsed["entity"]
            entities_data.append(e if isinstance(e, dict) else {"label": str(e), "entity_type": "object"})

    elif isinstance(parsed, list):
        observations_data = [item for item in parsed if isinstance(item, dict)]

    for obs_item in observations_data:
        ent = obs_item.get("entity")
        if ent and isinstance(ent, (dict, str)):
            entities_data.append(ent if isinstance(ent, dict) else {"label": str(ent), "entity_type": "object"})
        ents = obs_item.get("entities")
        if isinstance(ents, list):
            for e in ents:
                if isinstance(e, (dict, str)):
                    entities_data.append(e if isinstance(e, dict) else {"label": str(e), "entity_type": "object"})

    if not observations_data and raw_content.strip():
        norm_desc = normalize_observation_description(raw_content)
        observations_data = [
            {
                "observation_type": "visual_detection",
                "description": norm_desc,
                "confidence": 0.85,
            }
        ]
        lower_desc = norm_desc.lower()
        if any(w in lower_desc for w in ("person", "man", "woman", "individual", "pedestrian", "suspect")):
            entities_data.append({
                "entity_type": "person",
                "label": "Person-1",
                "attributes": {"detection_source": "visual_narrative"},
            })
        if any(w in lower_desc for w in ("car", "vehicle", "sedan", "truck", "suv", "van", "motorcycle")):
            entities_data.append({
                "entity_type": "vehicle",
                "label": "Vehicle-1",
                "attributes": {"detection_source": "visual_narrative"},
            })
        if any(w in lower_desc for w in ("dog", "cat", "animal", "bird")):
            entities_data.append({
                "entity_type": "animal",
                "label": "Animal-1",
                "attributes": {"detection_source": "visual_narrative"},
            })

    return observations_data, entities_data


_GENERIC_ENTITY_LABELS: frozenset[str] = frozenset({
    "person",
    "vehicle",
    "animal",
    "object",
    "unknown",
    "subject",
    "car",
    "man",
    "woman",
    "individual",
    "pedestrian",
})


def _is_specific_label(label: str | None, entity_type: str) -> bool:
    """Determine whether an entity label is informative rather than a generic placeholder."""
    if not label:
        return False
    cleaned = label.strip()
    if not cleaned or cleaned.lower() in _GENERIC_ENTITY_LABELS:
        return False
    # Auto-generated prefix patterns like person_ent-123 or ent-abc
    if cleaned.startswith(f"{entity_type}_ent-") or cleaned.startswith("ent-"):
        return False
    return True


def resolve_or_create_entity(
    repository: Any,
    entity_info: dict[str, Any] | str,
    obs_id: str,
    active_entities: dict[str, Entity],
) -> Entity:
    """Conservatively resolve or create an entity record within an investigation.

    Rules:
    1. Reuse verified explicit entity references if supplied.
    2. Match against active scoped entities by matching entity_type and specific label,
       or strong non-conflicting multi-attribute overlap.
    3. Do NOT merge based solely on generic labels or single clothing color.
    4. Preserve unresolved entities when uncertain.
    5. Safely merge attributes and update associated_observation_ids without duplicates.
    """
    if isinstance(entity_info, str):
        raw_str = entity_info.strip()
        lower_str = raw_str.lower()
        if any(w in lower_str for w in ("car", "vehicle", "truck", "sedan", "van", "motorcycle", "bike")):
            e_type = "vehicle"
        elif any(w in lower_str for w in ("person", "man", "woman", "individual", "pedestrian", "suspect")):
            e_type = "person"
        elif any(w in lower_str for w in ("dog", "cat", "animal", "bird")):
            e_type = "animal"
        else:
            e_type = "object"
        entity_info = {"entity_type": e_type, "label": raw_str, "attributes": {"description": raw_str}}

    raw_type = str(
        entity_info.get("entity_type")
        or entity_info.get("category")
        or entity_info.get("type")
        or "person"
    ).strip().lower()
    # Normalize common synonyms
    if raw_type in {"human", "pedestrian", "man", "woman", "suspect", "individual"}:
        raw_type = "person"
    elif raw_type in {"car", "truck", "motorcycle", "automobile", "bus", "van", "sedan"}:
        raw_type = "vehicle"

    valid_types = {"person", "vehicle", "animal", "object", "unknown"}
    entity_type = raw_type if raw_type in valid_types else "unknown"

    raw_attributes = entity_info.get("attributes", {})
    attributes: dict[str, Any] = (
        dict(raw_attributes) if isinstance(raw_attributes, dict) else {}
    )
    # Sanitize attributes according to Entity schema (non-blank keys, finite values, stringified nested data)
    clean_attributes: dict[str, Any] = {}
    for k, v in attributes.items():
        if isinstance(k, str) and k.strip():
            if isinstance(v, (dict, list)):
                v = json.dumps(v)
            elif isinstance(v, float) and not math.isfinite(v):
                continue
            clean_attributes[k.strip()] = v

    candidate_label = str(entity_info.get("label", "")).strip() or None
    is_cand_specific = _is_specific_label(candidate_label, entity_type)

    matched_entity: Entity | None = None

    # 1. Explicit verified reference
    explicit_id = entity_info.get("entity_id")
    if explicit_id and str(explicit_id) in active_entities:
        existing = active_entities[str(explicit_id)]
        if existing.entity_type == entity_type:
            matched_entity = existing

    # 2. Heuristic resolution if not explicitly resolved
    if matched_entity is None:
        for existing in active_entities.values():
            if existing.entity_type != entity_type:
                continue

            # Check for hard attribute conflicts
            has_conflict = False
            matching_attr_count = 0
            for k, v in clean_attributes.items():
                if k in existing.attributes:
                    ev = existing.attributes[k]
                    if v is not None and ev is not None:
                        str_v = str(v).strip().lower()
                        str_ev = str(ev).strip().lower()
                        if str_v != str_ev:
                            has_conflict = True
                            break
                        matching_attr_count += 1

            if has_conflict:
                continue

            # Case A: Same specific label (e.g. Suspect-1, Vehicle-1) without conflict
            is_exist_specific = _is_specific_label(existing.label, entity_type)
            if (
                is_cand_specific
                and is_exist_specific
                and candidate_label is not None
                and existing.label is not None
                and candidate_label.strip().lower() == existing.label.strip().lower()
            ):
                matched_entity = existing
                break

            # Case B: Multi-attribute match (at least 2 distinctive matching attributes)
            if matching_attr_count >= 2:
                matched_entity = existing
                break

            # Case C: Distinctive single attribute such as license_plate or id_badge
            for distinctive_key in ("license_plate", "plate", "id_badge", "badge_number"):
                if (
                    distinctive_key in clean_attributes
                    and clean_attributes[distinctive_key]
                    and distinctive_key in existing.attributes
                    and str(clean_attributes[distinctive_key]).strip().lower()
                    == str(existing.attributes[distinctive_key]).strip().lower()
                ):
                    matched_entity = existing
                    break
            if matched_entity is not None:
                break

    # 3. Update existing or create new
    if matched_entity is not None:
        # Avoid duplicate observation IDs
        new_obs_ids = list(matched_entity.associated_observation_ids)
        if obs_id not in new_obs_ids:
            new_obs_ids.append(obs_id)

        # Merge attributes without losing existing attributes
        merged_attributes = dict(matched_entity.attributes)
        for k, v in clean_attributes.items():
            if k not in merged_attributes or merged_attributes[k] in (None, ""):
                merged_attributes[k] = v

        # Update label if existing was generic and candidate is specific
        new_label = matched_entity.label
        if (
            not _is_specific_label(matched_entity.label, entity_type)
            and is_cand_specific
            and candidate_label is not None
        ):
            new_label = candidate_label

        updated_entity = Entity(
            entity_id=matched_entity.entity_id,
            entity_type=matched_entity.entity_type,
            label=new_label,
            attributes=merged_attributes,
            associated_observation_ids=new_obs_ids,
        )
        repository.add_entity(updated_entity)
        active_entities[updated_entity.entity_id] = updated_entity
        return updated_entity

    # Create new entity record
    new_ent_id = f"ent-{uuid.uuid4().hex[:8]}"
    default_label = candidate_label or f"{entity_type}_{new_ent_id[:6]}"
    new_entity = Entity(
        entity_id=new_ent_id,
        entity_type=entity_type,  # type: ignore[arg-type]
        label=default_label,
        attributes=clean_attributes,
        associated_observation_ids=[obs_id],
    )
    repository.add_entity(new_entity)
    active_entities[new_entity.entity_id] = new_entity
    return new_entity


class VisualDetectorWorker(BaseToolWorker):
    """Analyzes image/frame artifacts using vision models to produce Observations and Entities."""

    @staticmethod
    def _select_evenly_spaced_artifacts(
        artifacts: list[Artifact],
        limit: int,
    ) -> list[str]:
        """Sort artifacts chronologically and select evenly spaced items across the timeline."""
        if not artifacts or limit <= 0:
            return []
        sorted_arts = sorted(
            artifacts,
            key=lambda a: (
                a.source_reference.start_seconds
                if a.source_reference and a.source_reference.start_seconds is not None
                else 0.0
            ),
        )
        if len(sorted_arts) <= limit:
            return [a.artifact_id for a in sorted_arts]
        if limit == 1:
            return [sorted_arts[0].artifact_id]

        step = (len(sorted_arts) - 1) / (limit - 1)
        indices = [int(round(i * step)) for i in range(limit)]
        selected: list[str] = []
        seen: set[int] = set()
        for idx in indices:
            if idx not in seen and 0 <= idx < len(sorted_arts):
                seen.add(idx)
                selected.append(sorted_arts[idx].artifact_id)
        if len(selected) < limit:
            for a in sorted_arts:
                if a.artifact_id not in selected:
                    selected.append(a.artifact_id)
                    if len(selected) == limit:
                        break
        return selected

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
                m_arts: list[Artifact] = []
                for aid in m_aids:
                    try:
                        m_arts.append(self.repository.get_artifact(aid))
                    except Exception:
                        pass
                if m_arts:
                    balanced_ids.extend(self._select_evenly_spaced_artifacts(m_arts, per_media_limit))
                else:
                    balanced_ids.extend(m_aids[:per_media_limit])
            artifact_ids = balanced_ids
        else:
            all_arts_list: list[Artifact] = []
            for aid in artifact_ids:
                try:
                    all_arts_list.append(self.repository.get_artifact(aid))
                except Exception:
                    pass
            if all_arts_list:
                artifact_ids = self._select_evenly_spaced_artifacts(all_arts_list, max_frames_per_task)
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

        # Collect existing entities scoped to this investigation for conservative resolution
        scoped_obs_ids: set[str] = set()
        if investigation_id:
            try:
                state = self.repository.get_state(str(investigation_id))
                if state is not None:
                    scoped_obs_ids.update(state.observation_ids)
            except Exception:
                pass
            if not scoped_obs_ids:
                try:
                    inv = self.repository.get_investigation(str(investigation_id))
                    target_media = set(inv.media_asset_ids)
                    for o in self.repository.list_observations():
                        if any(
                            sr.media_asset_id in target_media
                            for sr in o.source_references
                        ):
                            scoped_obs_ids.add(o.observation_id)
                except Exception:
                    pass

        all_entities = self.repository.list_entities()
        active_entities: dict[str, Entity] = {}
        for ent in all_entities:
            if not scoped_obs_ids or any(
                oid in scoped_obs_ids for oid in ent.associated_observation_ids
            ):
                active_entities[ent.entity_id] = ent

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

            # Validate storage URI
            uri = artifact.storage_uri
            _is_resolvable = False
            # Mock LLM operates without physical files
            is_mock_llm = type(self.llm).__name__ == "MockLLMClient"
            if is_mock_llm:
                _is_resolvable = True
            elif uri.startswith("http://") or uri.startswith("https://"):
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

            analysis_status = "analyzed"
            failure_reason = ""

            if not _is_resolvable:
                analysis_status = "failed"
                failure_reason = f"Unresolvable storage URI '{uri}'"
                logger.warning(
                    "VisualDetectorWorker: artifact %s has unresolvable storage URI '%s'; "
                    "recording analysis_failed observation.",
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
                    analysis_status = "failed"
                    failure_reason = f"VLM call failed: {exc}"
                    logger.warning(
                        "VisualDetectorWorker: frame %s VLM call failed (%s); "
                        "recording analysis_failed observation.",
                        art_id,
                        exc,
                    )
                    raw_content = ""

            # Distinguish outcomes: analyzed-with-findings, analyzed-clean, analysis_failed
            if analysis_status == "failed":
                observations_data = [
                    {
                        "observation_type": "analysis_failed",
                        "description": f"Visual inspection failed: {failure_reason}",
                        "confidence": 0.0,
                    }
                ]
                frame_entities = []
            else:
                observations_data, frame_entities = parse_vlm_detection_response(raw_content)
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
                raw_desc = str(obs_item.get("description", "Salient visual detection."))
                clean_desc = normalize_observation_description(raw_desc)
                # Prepend camera context if not already present
                if cam_label and cam_label not in clean_desc:
                    desc = f"{cam_label} {clean_desc}"
                else:
                    desc = clean_desc

                confidence = parse_confidence(
                    obs_item.get("confidence"),
                    default=0.90 if obs_type != "analysis_failed" else 0.0,
                )

                method_str = "visual_detection_failed" if obs_type == "analysis_failed" else "visual_detection"
                provenance = Provenance(
                    producer_type="vision_model",
                    producer_name=getattr(self.llm, "model_name", "vision_model")
                    or "vision_model",
                    method=method_str,
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

                # Process candidate entities only for successful detections
                if obs_type != "analysis_failed":
                    item_entities: list[dict[str, Any] | str] = []
                    if obs_item.get("entity"):
                        item_entities.append(obs_item["entity"])
                    if isinstance(obs_item.get("entities"), list):
                        item_entities.extend(obs_item["entities"])
                    item_entities.extend(frame_entities)

                    for ent_info in item_entities:
                        if isinstance(ent_info, (dict, str)):
                            resolve_or_create_entity(
                                repository=self.repository,
                                entity_info=ent_info,
                                obs_id=obs_id,
                                active_entities=active_entities,
                            )

        return output_observation_ids
