"""Forensic report generator worker synthesizing investigation findings."""

from __future__ import annotations

import logging
import uuid

from vigil.domain.report import Report
from vigil.orchestration.task_types import TaskRequest
from vigil.storage.repository import EntityNotFoundError
from vigil.tools.base import BaseToolWorker

logger = logging.getLogger(__name__)


def _format_timecode(seconds: float | None) -> str:
    """Format seconds into MM:SS.ss timecode."""
    if seconds is None:
        return "N/A"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins:02d}:{secs:05.2f}"


def _clean_summary_output(text: str) -> str:
    """Clean markdown artifacts, code fence wrappers, or raw echoes from LLM summary."""
    if not text:
        return ""
    cleaned = text.strip()
    if cleaned.startswith("```markdown"):
        cleaned = cleaned[len("```markdown"):].strip()
    elif cleaned.startswith("```"):
        cleaned = cleaned[len("```"):].strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    return cleaned


class ReportGeneratorWorker(BaseToolWorker):
    """Compiles observations, events, assessments, and coverage into a structured Report."""

    def run(self, request: TaskRequest) -> list[str]:
        investigation_id = str(
            request.parameters.get("investigation_id", "inv-default")
        )
        title = str(
            request.parameters.get(
                "title", f"Forensic Investigation Report: {investigation_id}"
            )
        )

        # Retrieve investigation details if available
        inv_title = title
        media_asset_ids: list[str] = []
        try:
            inv = self.repository.get_investigation(investigation_id)
            objective = inv.objective or "Forensic timeline and activity verification."
            inv_title = inv.title or title
            media_asset_ids = list(inv.media_asset_ids)
        except EntityNotFoundError:
            objective = "Forensic timeline and activity verification."

        # Collect scoped references for THIS investigation
        state = self.repository.get_state(investigation_id)
        if state is not None:
            obs_ids = list(state.observation_ids)
            event_ids = list(state.event_ids)
        else:
            obs_ids = []
            event_ids = []

        # If state did not track observations yet, check media asset references
        if not obs_ids and media_asset_ids:
            all_obs = self.repository.list_observations()
            for o in all_obs:
                if any(sr.media_asset_id in media_asset_ids for sr in o.source_references):
                    obs_ids.append(o.observation_id)

        # Retrieve scoped records
        observations = self.repository.list_observations(obs_ids) if obs_ids else []
        events = self.repository.list_events(event_ids) if event_ids else []

        # Filter assessments strictly targeting this case's events or observations
        target_ids = set(event_ids) | set(obs_ids)
        all_assessments = self.repository.list_evidence_assessments()
        assessments = [a for a in all_assessments if a.target_id in target_ids]
        assessment_ids = [a.assessment_id for a in assessments]

        coverages = self.repository.list_coverage_records(investigation_id)
        coverage_ids = [c.coverage_id for c in coverages]

        # Gather all media assets and camera information
        all_repo_assets = {m.media_asset_id: m for m in self.repository.list_media_assets()}
        all_media = [all_repo_assets[mid] for mid in media_asset_ids if mid in all_repo_assets]
        camera_map = {c.camera_id: c for c in self.repository.list_cameras()}

        media_context_lines = []
        for m in all_media:
            cam_info = ""
            if m.camera_id and m.camera_id in camera_map:
                c = camera_map[m.camera_id]
                cam_info = f" [Camera: {c.camera_id} - {c.location_label or c.name}]"
            elif m.camera_id:
                cam_info = f" [Camera: {m.camera_id}]"
            dur_str = f"{m.duration_seconds:.1f}s" if m.duration_seconds else "N/A"
            media_context_lines.append(f"- Media Asset '{m.media_asset_id}'{cam_info}: Duration {dur_str}")
        media_context = "\n".join(media_context_lines) if media_context_lines else "- Single primary surveillance feed"

        # Chronological ordering of events
        sorted_events = sorted(
            events,
            key=lambda e: (e.start_seconds if e.start_seconds is not None else 0.0),
        )

        events_summary_lines: list[str] = []
        for e in sorted_events:
            t_str = ""
            if e.start_seconds is not None and e.end_seconds is not None:
                t_str = f"[{_format_timecode(e.start_seconds)} - {_format_timecode(e.end_seconds)} ({e.start_seconds:.1f}s - {e.end_seconds:.1f}s)]"
            elif e.start_seconds is not None:
                t_str = f"[{e.start_seconds:.1f}s]"
            events_summary_lines.append(
                f"- {t_str} Event: {e.event_type} (Status: {e.status}) — {e.description} (Supporting observations: {len(e.observation_ids)})"
            )
        events_context = "\n".join(events_summary_lines) if events_summary_lines else "No discrete correlated events."

        obs_summary_lines: list[str] = []
        for o in observations[:25]:
            sr = o.source_references[0] if o.source_references else None
            t_str = ""
            if sr and sr.start_seconds is not None and sr.end_seconds is not None:
                t_str = f"[{_format_timecode(sr.start_seconds)} - {_format_timecode(sr.end_seconds)}]"
            elif sr and sr.start_seconds is not None:
                t_str = f"[{sr.start_seconds:.1f}s]"
            obs_summary_lines.append(
                f"- {t_str} Modality: {o.modality} | Finding: {o.observation_type} | Conf: {o.confidence or 0.85:.2f} | {o.description}"
            )
        obs_context = "\n".join(obs_summary_lines) if obs_summary_lines else "No observations recorded."

        assessments_summary_lines: list[str] = []
        for a in assessments[:15]:
            assessments_summary_lines.append(
                f"- Target: {a.target_type}:{a.target_id} | Rating: {a.rating.upper()} | Dimension: {a.assessment_type} | Rationale: {a.rationale}"
            )
        assessments_context = "\n".join(assessments_summary_lines) if assessments_summary_lines else "No formal evidence assessments recorded."

        # Structured synthesis prompt
        prompt = (
            "You are a lead forensic investigator writing the official Executive Summary and Findings for a video-forensic report.\n\n"
            f"CASE INFORMATION:\n"
            f"- Title: {inv_title}\n"
            f"- Investigation Objective: '{objective}'\n\n"
            f"EXAMINED PREMISE CAMERA FEEDS ({len(all_media)} Feed(s)):\n"
            f"{media_context}\n\n"
            f"EXAMINED EVIDENCE SCOPE (STRICT DATA FOR THIS CASE):\n"
            f"- Observations count: {len(obs_ids)}\n"
            f"- Correlated Events count: {len(event_ids)}\n"
            f"- Evidence Assessments count: {len(assessment_ids)}\n"
            f"- Coverage Records count: {len(coverage_ids)}\n\n"
            f"CHRONOLOGICAL EVENT TIMELINE (ACROSS PREMISE FEEDS):\n{events_context}\n\n"
            f"OBSERVATIONAL EVIDENCE:\n{obs_context}\n\n"
            f"EVIDENCE ASSESSMENTS:\n{assessments_context}\n\n"
            "INSTRUCTIONS:\n"
            "Write an authoritative, clear, and easy-to-interpret forensic investigation summary. "
            "Follow this exact structured format with markdown headers and bullet points:\n\n"
            "### 1. Objective Finding & Direct Answer\n"
            f"Provide a clear, decisive, and unambiguous answer to the Investigation Objective ('{objective}'). "
            "State the primary finding, counts of persons/entities, and verified conclusions immediately across all premise feeds.\n\n"
            "### 2. Chronological Timeline Analysis\n"
            "Detail the sequence of occurrences in chronological order using timestamp intervals [MM:SS or seconds]. "
            "Highlight entity movement and progression across different camera viewpoints and locations on the premise. "
            "Correlate visual and acoustic observations with physical actions.\n\n"
            "### 3. Evidence Integrity & Confidence\n"
            "Summarize the evidence quality, support level, and certainty of the findings based on the verified data.\n\n"
            "STRICT RULES:\n"
            f"- DO NOT hallucinate records or counts. The total observations examined is exactly {len(obs_ids)}, "
            f"the discrete events is {len(event_ids)}, and assessments is {len(assessment_ids)}.\n"
            "- Strictly ground all conclusions in the timestamped evidence provided above."
        )

        # Baseline fallback summary
        feed_note = f" across {len(all_media)} camera feeds" if len(all_media) > 1 else ""
        summary = (
            f"### 1. Objective Finding & Direct Answer\n"
            f"Forensic investigation completed for objective: '{objective}'. Analysis identified {len(event_ids)} "
            f"discrete events{feed_note} supported by {len(obs_ids)} observations.\n\n"
            f"### 2. Chronological Timeline Analysis\n"
            f"{events_context}\n\n"
            f"### 3. Evidence Integrity & Confidence\n"
            f"Examination covered {len(coverage_ids)} source records across {len(all_media) or 1} surveillance feeds with {len(assessment_ids)} formal evidence assessments."
        )

        try:
            response = self.llm.generate_text(prompt=prompt, json_mode=False)
            if response and response.content and response.content.strip():
                clean_content = _clean_summary_output(response.content)
                if len(clean_content) > 30:
                    summary = clean_content
        except Exception as exc:
            logger.warning("ReportGeneratorWorker: LLM call failed (%s); using baseline summary.", exc)

        report_id = f"rep-{uuid.uuid4().hex[:8]}"
        report = Report(
            report_id=report_id,
            investigation_id=investigation_id,
            title=title,
            summary=summary,
            observation_ids=obs_ids,
            event_ids=event_ids,
            assessment_ids=assessment_ids,
            coverage_ids=coverage_ids,
            generated_by=str(
                request.parameters.get("generated_by", "vigil-lead-investigator")
            ),
        )

        self.repository.add_report(report)
        return [report_id]
