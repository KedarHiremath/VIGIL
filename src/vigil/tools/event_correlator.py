"""Temporal event correlation and relationship discovery worker."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from vigil.domain.event import Event
from vigil.domain.event_link import EventLink
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

        # Retrieve objective context
        obj_context = ""
        if investigation_id:
            try:
                inv = self.repository.get_investigation(str(investigation_id))
                if inv.objective:
                    obj_context = f"Investigation Objective: {inv.objective}\n"
            except Exception:
                pass

        # Correlate observations into events using LLM reasoning with timecode context
        obs_summary_lines = []
        for o in observations:
            sr = o.source_references[0] if o.source_references else None
            t_str = ""
            if sr and sr.start_seconds is not None and sr.end_seconds is not None:
                t_str = f"Timecode: [{_format_timecode(sr.start_seconds)} - {_format_timecode(sr.end_seconds)} ({sr.start_seconds:.1f}s-{sr.end_seconds:.1f}s)]"
            elif sr and sr.start_seconds is not None:
                t_str = f"Timecode: [{sr.start_seconds:.1f}s]"
            obs_summary_lines.append(
                f"- ID: {o.observation_id}, Modality: {o.modality}, Type: {o.observation_type}, {t_str}, Desc: {o.description}"
            )
        obs_summary = "\n".join(obs_summary_lines)

        prompt = (
            f"You are a forensic video timeline analyst. Correlate the following observations into discrete chronological events.\n"
            f"{obj_context}"
            f"Observations:\n{obs_summary}\n\n"
            "Group temporally and logically related observations into distinct events. "
            "Return JSON with 'events', each with: 'event_type', 'description', and 'observation_ids'. "
            "Also optional 'links' with 'from_event_index', 'to_event_index', 'relationship_type' "
            "(before/after/overlaps/related_to/possible_same_incident), and 'rationale'."
        )

        events_data: list[dict[str, Any]] = []
        links_data: list[dict[str, Any]] = []

        try:
            response = self.llm.generate_text(prompt=prompt, json_mode=True)
            if response and response.content:
                parsed = json.loads(response.content)
                if isinstance(parsed, dict):
                    events_data = parsed.get("events", [])
                    links_data = parsed.get("links", [])
                elif isinstance(parsed, list):
                    events_data = parsed
        except Exception as exc:
            logger.warning(
                "EventCorrelatorWorker: LLM correlation failed (%s); using fallback correlation.",
                exc,
            )
            events_data = []

        if not events_data:
            # Fallback: create a synthesized event grouping all current observations
            events_data = [
                {
                    "event_type": "incident_occurrence",
                    "description": "Correlated occurrence supported by visual and/or acoustic observations.",
                    "observation_ids": obs_ids,
                }
            ]

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
