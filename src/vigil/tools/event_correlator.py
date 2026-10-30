"""Temporal event correlation and relationship discovery worker."""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any

from vigil.domain.event import Event
from vigil.domain.event_link import EventLink
from vigil.domain.observation import Observation
from vigil.orchestration.task_types import TaskRequest
from vigil.tools.base import BaseToolWorker

logger = logging.getLogger(__name__)


def _format_timecode(seconds: float | None) -> str:
    """Format seconds into MM:SS.ss timecode."""
    if seconds is None:
        return "N/A"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins:02d}:{secs:05.2f}"


def parse_correlator_response(raw_text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse events and links from LLM response safely, handling code fences and JSON wrappers."""
    if not raw_text or not raw_text.strip():
        return [], []

    cleaned = raw_text.strip()
    if "```" in cleaned:
        fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", cleaned)
        if fence_match:
            cleaned = fence_match.group(1).strip()
        else:
            cleaned = re.sub(r"^```[a-z]*\s*", "", cleaned)
            cleaned = re.sub(r"\s*```$", "", cleaned).strip()

    # Find JSON boundaries
    json_str = cleaned
    if "{" in cleaned and "}" in cleaned:
        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        json_str = cleaned[start_idx : end_idx + 1]
    elif "[" in cleaned and "]" in cleaned:
        start_idx = cleaned.find("[")
        end_idx = cleaned.rfind("]")
        json_str = cleaned[start_idx : end_idx + 1]

    try:
        parsed = json.loads(json_str)
        if isinstance(parsed, dict):
            evs = parsed.get("events", [])
            links = parsed.get("links", [])
            valid_events = [e for e in evs if isinstance(e, dict) and (e.get("description") or e.get("event_type"))]
            valid_links = [l for l in links if isinstance(l, dict)]
            return valid_events, valid_links
        elif isinstance(parsed, list):
            valid_events = [e for e in parsed if isinstance(e, dict) and (e.get("description") or e.get("event_type"))]
            return valid_events, []
    except Exception:
        pass
    return [], []


def _cluster_fallback_events(
    observations: list[Observation],
    media_map: dict[str, Any],
    camera_map: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Forensically cluster observations into discrete chronological events with synthesized evidence summaries.

    Avoids monolithic single-event fallbacks or placeholder text.
    """
    if not observations:
        return [], []

    # 1. Filter out failed analyses if other valid observations exist
    valid_obs = [
        o for o in observations
        if o.observation_type != "analysis_failed" and (o.confidence is None or o.confidence > 0.0)
    ]
    if not valid_obs:
        valid_obs = observations

    # 2. Sort observations chronologically
    def _obs_start(o: Observation) -> float:
        if o.source_references and o.source_references[0].start_seconds is not None:
            return float(o.source_references[0].start_seconds)
        return 0.0

    valid_obs.sort(key=_obs_start)

    # 3. Check if all observations are clean inspections
    clean_count = sum(
        1 for o in valid_obs
        if "no salient" in o.description.lower() or "routine" in o.description.lower() or o.observation_type == "visual_inspection"
    )
    if clean_count == len(valid_obs):
        # Entire timeline analyzed without incident
        start_t = _obs_start(valid_obs[0])
        end_t = (
            valid_obs[-1].source_references[0].end_seconds
            if valid_obs[-1].source_references and valid_obs[-1].source_references[0].end_seconds is not None
            else start_t + 1.0
        )
        return [
            {
                "event_type": "routine_surveillance",
                "description": f"Routine surveillance coverage maintained across sector ({_format_timecode(start_t)} - {_format_timecode(end_t)}); no security anomalies detected.",
                "observation_ids": [o.observation_id for o in valid_obs],
            }
        ], []

    # 4. Group into chronological clusters (gap > 8.0s triggers a new event)
    clusters: list[list[Observation]] = []
    current_cluster: list[Observation] = []
    last_end = -1.0

    for obs in valid_obs:
        start_sec = _obs_start(obs)
        end_sec = (
            obs.source_references[0].end_seconds
            if obs.source_references and obs.source_references[0].end_seconds is not None
            else start_sec
        )

        if not current_cluster:
            current_cluster.append(obs)
            last_end = end_sec
        else:
            time_gap = start_sec - last_end
            if time_gap > 8.0 or len(current_cluster) >= 15:
                clusters.append(current_cluster)
                current_cluster = [obs]
                last_end = end_sec
            else:
                current_cluster.append(obs)
                last_end = max(last_end, end_sec)

    if current_cluster:
        clusters.append(current_cluster)

    # 5. Synthesize distinct forensic events for each cluster
    events_data: list[dict[str, Any]] = []

    for cluster in clusters:
        cluster_oids = [o.observation_id for o in cluster]
        c_start = _obs_start(cluster[0])
        c_end = max(
            (
                o.source_references[0].end_seconds
                if o.source_references and o.source_references[0].end_seconds is not None
                else _obs_start(o)
            )
            for o in cluster
        )

        # Camera context
        first_sr = cluster[0].source_references[0] if cluster[0].source_references else None
        cam_label = ""
        if first_sr and first_sr.media_asset_id in media_map:
            asset = media_map[first_sr.media_asset_id]
            if asset.camera_id and asset.camera_id in camera_map:
                cam = camera_map[asset.camera_id]
                cam_label = f"[{cam.location_label or cam.name or cam.camera_id}] "
            elif asset.camera_id:
                cam_label = f"[{asset.camera_id}] "

        # Determine dominant type and salient descriptions
        types_count: dict[str, int] = {}
        salient_descs: list[str] = []

        for o in cluster:
            t = o.observation_type
            types_count[t] = types_count.get(t, 0) + 1
            d = o.description.strip()
            # Clean camera prefixes from individual observation descriptions for synthesis
            clean_d = re.sub(r"^\[[^\]]+\]\s*", "", d)
            if "no salient" not in clean_d.lower() and clean_d not in salient_descs:
                salient_descs.append(clean_d)

        # Derive event_type
        dominant_type = max(types_count.keys(), key=lambda k: types_count[k]) if types_count else "visual_detection"
        if "person" in dominant_type:
            event_type = "person_activity"
        elif "vehicle" in dominant_type:
            event_type = "vehicle_movement"
        elif "acoustic" in dominant_type or "audio" in dominant_type:
            event_type = "acoustic_incident"
        elif "incident" in dominant_type or "intrusion" in dominant_type or "breach" in dominant_type:
            event_type = dominant_type
        else:
            event_type = "premise_activity"

        # Synthesize forensic summary
        if salient_descs:
            main_finding = salient_descs[0]
            if not main_finding.endswith("."):
                main_finding += "."
            if len(salient_descs) > 1:
                secondary = salient_descs[1]
                if not secondary.endswith("."):
                    secondary += "."
                desc = f"{cam_label}{main_finding} Corroborated by {len(cluster)} observation(s); {secondary}"
            else:
                desc = f"{cam_label}{main_finding} Corroborated by {len(cluster)} visual/acoustic observation(s)."
        else:
            desc = f"{cam_label}Monitored activity detected ({_format_timecode(c_start)} - {_format_timecode(c_end)}) across {len(cluster)} observation(s)."

        events_data.append(
            {
                "event_type": event_type,
                "description": desc,
                "observation_ids": cluster_oids,
            }
        )

    # 6. Generate sequential chronological links
    links_data: list[dict[str, Any]] = [
        {
            "from_event_index": i,
            "to_event_index": i + 1,
            "relationship_type": "before",
            "rationale": "Chronological progression in forensic timeline.",
        }
        for i in range(len(events_data) - 1)
    ]

    return events_data, links_data


class EventCorrelatorWorker(BaseToolWorker):
    """Synthesizes observations across timeline into Events and EventLinks."""

    def run(self, request: TaskRequest) -> list[str]:
        obs_ids = list(request.input_refs)
        investigation_id = request.parameters.get("investigation_id")

        if not obs_ids and investigation_id:
            state = self.repository.get_state(str(investigation_id))
            if state and state.observation_ids:
                obs_ids = list(state.observation_ids)

        if not obs_ids and investigation_id:
            try:
                inv = self.repository.get_investigation(str(investigation_id))
                target_media_ids = set(inv.media_asset_ids)
                all_obs = self.repository.list_observations()
                for o in all_obs:
                    if any(sr.media_asset_id in target_media_ids for sr in o.source_references):
                        obs_ids.append(o.observation_id)
            except Exception:
                pass

        if not obs_ids:
            all_obs = self.repository.list_observations()
            if not all_obs:
                raise ValueError(
                    "No observations available in repository for correlation."
                )
            obs_ids = [o.observation_id for o in all_obs]

        observations = [self.repository.get_observation(oid) for oid in obs_ids]

        # Lookup tables for camera and media metadata
        media_map = {m.media_asset_id: m for m in self.repository.list_media_assets()}
        camera_map = {c.camera_id: c for c in self.repository.list_cameras()}

        # Retrieve objective context
        obj_context = ""
        if investigation_id:
            try:
                inv = self.repository.get_investigation(str(investigation_id))
                if inv.objective:
                    obj_context = f"Investigation Objective: {inv.objective}\n"
            except Exception:
                pass

        # Correlate observations into events using LLM reasoning with timecode and camera context
        obs_summary_lines = []
        for o in observations:
            sr = o.source_references[0] if o.source_references else None
            t_str = ""
            cam_info = ""
            if sr:
                if sr.start_seconds is not None and sr.end_seconds is not None:
                    t_str = f"Timecode: [{_format_timecode(sr.start_seconds)} - {_format_timecode(sr.end_seconds)} ({sr.start_seconds:.1f}s-{sr.end_seconds:.1f}s)]"
                elif sr.start_seconds is not None:
                    t_str = f"Timecode: [{sr.start_seconds:.1f}s]"
                if sr.media_asset_id in media_map:
                    asset = media_map[sr.media_asset_id]
                    if asset.camera_id and asset.camera_id in camera_map:
                        cam = camera_map[asset.camera_id]
                        cam_info = f"Camera: {cam.camera_id} ({cam.location_label or cam.name}), "
                    elif asset.camera_id:
                        cam_info = f"Camera: {asset.camera_id}, "

            obs_summary_lines.append(
                f"- ID: {o.observation_id}, Modality: {o.modality}, Type: {o.observation_type}, {cam_info}{t_str}, Desc: {o.description}"
            )
        obs_summary = "\n".join(obs_summary_lines)

        prompt = (
            "You are a forensic multi-video timeline and premise security analyst.\n"
            "Analyze and synthesize the following observations across all cameras and feeds into distinct, "
            "concrete MAJOR EVIDENCE EVENTS.\n"
            f"{obj_context}"
            f"Observations from Premise Feeds:\n{obs_summary}\n\n"
            "CRITICAL FORENSIC INSTRUCTIONS:\n"
            "1. Group temporally and logically related observations into distinct major evidence events. "
            "Do NOT lump the entire timeline into a single generic event.\n"
            "2. Identify specific activities (e.g., person movement, vehicle arrival/departure, perimeter entry, acoustic alarms, object manipulation).\n"
            "3. For each event provide:\n"
            "   - 'event_type': Specific category (e.g. 'person_activity', 'vehicle_movement', 'perimeter_entry', 'acoustic_alert', 'loitering')\n"
            "   - 'description': Clear, factual summary identifying who/what was observed, action taken, and camera location (e.g., 'Person in dark attire observed walking along North Fence toward gate.').\n"
            "   - 'observation_ids': List of specific observation IDs directly supporting this distinct occurrence.\n"
            "4. Return a valid JSON object strictly matching:\n"
            "{\n"
            '  "events": [\n'
            '    {"event_type": "...", "description": "...", "observation_ids": ["..."]}\n'
            "  ],\n"
            '  "links": [\n'
            '    {"from_event_index": 0, "to_event_index": 1, "relationship_type": "before", "rationale": "..."}\n'
            "  ]\n"
            "}"
        )

        events_data: list[dict[str, Any]] = []
        links_data: list[dict[str, Any]] = []

        try:
            response = self.llm.generate_text(prompt=prompt, json_mode=True)
            if response and response.content:
                events_data, links_data = parse_correlator_response(response.content)
        except Exception as exc:
            logger.warning(
                "EventCorrelatorWorker: LLM correlation failed (%s); using forensic clustering fallback.",
                exc,
            )
            events_data = []

        if not events_data:
            logger.info("EventCorrelatorWorker: applying temporal forensic clustering to synthesize major evidence events.")
            events_data, links_data = _cluster_fallback_events(
                observations=observations,
                media_map=media_map,
                camera_map=camera_map,
            )

        created_event_ids: list[str] = []
        created_events: list[Event] = []

        for idx, ev_info in enumerate(events_data):
            supporting_obs = ev_info.get("observation_ids", [])
            # Validate that supporting_obs is non-empty and exists
            valid_supporting_obs = [oid for oid in supporting_obs if oid in obs_ids]
            if not valid_supporting_obs:
                valid_supporting_obs = (
                    obs_ids[:1] if obs_ids else [observations[0].observation_id]
                )

            # Find entities associated with these observations
            associated_entity_ids: list[str] = []
            for ent in self.repository.list_entities():
                if any(
                    oid in ent.associated_observation_ids
                    for oid in valid_supporting_obs
                ):
                    associated_entity_ids.append(ent.entity_id)

            ev_id = f"evt-{uuid.uuid4().hex[:8]}"
            now = datetime.now(UTC)

            # Calculate start_seconds and end_seconds from supporting observations
            start_sec_candidates: list[float] = []
            end_sec_candidates: list[float] = []
            for oid in valid_supporting_obs:
                try:
                    obs = self.repository.get_observation(oid)
                    for sr in obs.source_references:
                        if sr.start_seconds is not None:
                            start_sec_candidates.append(sr.start_seconds)
                        if sr.end_seconds is not None:
                            end_sec_candidates.append(sr.end_seconds)
                except Exception:
                    pass

            ev_start_sec = min(start_sec_candidates) if start_sec_candidates else None
            ev_end_sec = max(end_sec_candidates) if end_sec_candidates else None
            if ev_start_sec is not None and ev_end_sec is not None and ev_end_sec <= ev_start_sec:
                ev_end_sec = ev_start_sec + 1.0

            event = Event(
                event_id=ev_id,
                event_type=str(ev_info.get("event_type", "incident_occurrence")),
                description=str(
                    ev_info.get("description", "Correlated forensic occurrence.")
                ),
                observation_ids=valid_supporting_obs,
                entity_ids=associated_entity_ids,
                status="proposed",
                start_time=now,
                end_time=now,
                start_seconds=ev_start_sec,
                end_seconds=ev_end_sec,
            )

            self.repository.add_event(event)
            created_event_ids.append(ev_id)
            created_events.append(event)

        # Create event links if multiple events exist
        if len(created_events) >= 2:
            # Process returned links or generate chronological sequence
            if links_data:
                for link_info in links_data:
                    from_idx = int(link_info.get("from_event_index", 0))
                    to_idx = int(link_info.get("to_event_index", 1))
                    rel_type = link_info.get("relationship_type", "before")
                    valid_rels = {
                        "before",
                        "after",
                        "overlaps",
                        "related_to",
                        "possible_same_incident",
                    }
                    rel_type = rel_type if rel_type in valid_rels else "related_to"

                    if (
                        0 <= from_idx < len(created_events)
                        and 0 <= to_idx < len(created_events)
                        and from_idx != to_idx
                    ):
                        link_id = f"link-{uuid.uuid4().hex[:8]}"
                        link = EventLink(
                            event_link_id=link_id,
                            from_event_id=created_events[from_idx].event_id,
                            to_event_id=created_events[to_idx].event_id,
                            relationship_type=rel_type,  # type: ignore[arg-type]
                            rationale=str(
                                link_info.get(
                                    "rationale", "Temporal association identified."
                                )
                            ),
                            confidence=0.85,
                        )
                        self.repository.add_event_link(link)
            else:
                # Default pairwise link
                link_id = f"link-{uuid.uuid4().hex[:8]}"
                link = EventLink(
                    event_link_id=link_id,
                    from_event_id=created_events[0].event_id,
                    to_event_id=created_events[1].event_id,
                    relationship_type="before",
                    rationale="Chronological occurrence in observation timeline.",
                    confidence=0.85,
                )
                self.repository.add_event_link(link)

        return created_event_ids
