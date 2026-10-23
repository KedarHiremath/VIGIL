"""Evidence quality, support level, and uncertainty assessment worker."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from typing import Any

from vigil.domain.evidence_assessment import EvidenceAssessment
from vigil.orchestration.task_types import TaskRequest
from vigil.tools.base import BaseToolWorker

logger = logging.getLogger(__name__)


def clean_rationale_text(text: str) -> str:
    """Strip raw markdown headers, bold labels, and repetitive prefixes from LLM rationale."""
    if not text:
        return ""
    # Strip markdown bold tags or explicit rating/rationale headers
    cleaned = re.sub(r"\*\*Rating\s*:\s*[^\*]+\*\*", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\*\*Rationale\s*:\s*\*\*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(Rating\s*:\s*[^\n]+\n?)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(Rationale\s*:\s*)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^[\s\-*•]+", "", cleaned.strip())
    # Clean redundant internal newlines or list dashes
    lines = [line.strip().lstrip("-*• ") for line in cleaned.splitlines() if line.strip()]
    cleaned_text = " ".join(lines)
    return cleaned_text or text.strip()


def extract_rating(text: str, default: str = "moderate") -> str:
    """Extract standard evidence rating from LLM response."""
    valid_ratings = {"insufficient", "low", "moderate", "high"}
    lower = text.lower()
    match = re.search(r"rating\s*[:=\-]?\s*\*?\*?\s*(insufficient|low|moderate|high)", lower)
    if match:
        return match.group(1)
    for r in ["insufficient", "high", "moderate", "low"]:
        if re.search(rf"\b{r}\b", lower):
            return r
    return default


class EvidenceAssessorWorker(BaseToolWorker):
    """Evaluates observations and events for evidence quality, support level, and uncertainty."""

    def run(self, request: TaskRequest) -> list[str]:
        target_ids = list(request.input_refs)
        investigation_id = request.parameters.get("investigation_id")

        if not target_ids and investigation_id:
            state = self.repository.get_state(str(investigation_id))
            if state:
                if state.event_ids:
                    target_ids = list(state.event_ids)
                elif state.observation_ids:
                    target_ids = list(state.observation_ids[:4])

        if not target_ids:
            # Fallback to repository events then observations
            events = self.repository.list_events()
            if events:
                target_ids = [e.event_id for e in events]
            else:
                obs = self.repository.list_observations()
                if obs:
                    target_ids = [o.observation_id for o in obs[:3]]
                else:
                    raise ValueError("No targets available for evidence assessment.")

        # Cap the number of API calls: assess at most 5 targets to avoid
        # flooding the NVIDIA NIM free-tier queue with unbounded requests.
        _MAX_ASSESSMENTS = int(os.environ.get("VIGIL_MAX_ASSESSMENTS", "5"))
        if len(target_ids) > _MAX_ASSESSMENTS:
            logger.info(
                "EvidenceAssessorWorker: capping assessment targets from %d to %d "
                "to respect API rate limits.",
                len(target_ids),
                _MAX_ASSESSMENTS,
            )
            target_ids = target_ids[:_MAX_ASSESSMENTS]

        assessor_name = str(
            request.parameters.get("assessed_by", "vigil-forensic-assessor")
        )
        output_assessment_ids: list[str] = []

        all_events = self.repository.list_events()
        event_map = {e.event_id: e for e in all_events}
        all_obs = self.repository.list_observations()
        obs_map = {o.observation_id: o for o in all_obs}

        for target_id in target_ids:
            if target_id in event_map:
                target_type = "event"
                target_record = event_map[target_id]
                time_ctx = ""
                if target_record.start_seconds is not None and target_record.end_seconds is not None:
                    time_ctx = f" (Footage interval: {target_record.start_seconds:.1f}s - {target_record.end_seconds:.1f}s)"
                prompt = (
                    f"You are a video forensics assessor. Evaluate evidence quality and certainty for this event{time_ctx}:\n"
                    f"Event Type: {target_record.event_type}\n"
                    f"Description: {target_record.description}\n"
                    f"Supporting Observations: {len(target_record.observation_ids)}\n\n"
                    "Rate the evidence quality based on visual/acoustic clarity and observability.\n"
                    "Provide a JSON object with:\n"
                    "  'rating': one of 'high', 'moderate', 'low', 'insufficient'\n"
                    "  'assessment_type': one of 'evidence_quality', 'support_level', 'uncertainty'\n"
                    "  'rationale': concise factual explanation (1-2 sentences) of evidence strength and any ambiguity, without markdown headers or prefixes."
                )
            elif target_id in obs_map:
                target_type = "observation"
                target_record = obs_map[target_id]
                time_ctx = ""
                if target_record.source_references:
                    sr0 = target_record.source_references[0]
                    if sr0.start_seconds is not None and sr0.end_seconds is not None:
                        time_ctx = f" (Footage interval: {sr0.start_seconds:.1f}s - {sr0.end_seconds:.1f}s)"
                prompt = (
                    f"You are a video forensics assessor. Evaluate evidence quality for this observation{time_ctx}:\n"
                    f"Modality: {target_record.modality}\n"
                    f"Type: {target_record.observation_type}\n"
                    f"Description: {target_record.description}\n"
                    f"Confidence: {target_record.confidence}\n\n"
                    "Provide a JSON object with:\n"
                    "  'rating': one of 'high', 'moderate', 'low', 'insufficient'\n"
                    "  'assessment_type': one of 'evidence_quality', 'support_level', 'uncertainty'\n"
                    "  'rationale': concise factual explanation (1-2 sentences) of finding reliability without markdown headers or prefixes."
                )
            else:
                continue

            rating = "high"
            ass_type = "evidence_quality"
            rationale_text = "Standard forensic quality assessment verified against footage telemetry."

            try:
                response = self.llm.generate_text(prompt=prompt, json_mode=True)
                if response and response.content and response.content.strip():
                    raw = response.content.strip()
                    try:
                        parsed = json.loads(raw)
                        if isinstance(parsed, dict):
                            r = str(parsed.get("rating", "")).lower().strip()
                            if r in {"insufficient", "low", "moderate", "high"}:
                                rating = r
                            at = str(parsed.get("assessment_type", "")).lower().strip()
                            if at in {"evidence_quality", "support_level", "uncertainty"}:
                                ass_type = at
                            parsed_rat = clean_rationale_text(str(parsed.get("rationale", "")))
                            if parsed_rat:
                                rationale_text = parsed_rat
                    except Exception:
                        rating = extract_rating(raw, default="high")
                        rationale_text = clean_rationale_text(raw)
            except Exception as exc:
                logger.warning(
                    "EvidenceAssessorWorker: LLM call failed (%s); using baseline assessment.",
                    exc,
                )

            assessment_id = f"asm-{uuid.uuid4().hex[:8]}"
            assessment = EvidenceAssessment(
                assessment_id=assessment_id,
                target_type=target_type,  # type: ignore[arg-type]
                target_id=target_id,
                assessment_type=ass_type,  # type: ignore[arg-type]
                rating=rating,  # type: ignore[arg-type]
                rationale=rationale_text,
                assessed_by=assessor_name,
            )

            self.repository.add_evidence_assessment(assessment)
            output_assessment_ids.append(assessment_id)

        return output_assessment_ids
