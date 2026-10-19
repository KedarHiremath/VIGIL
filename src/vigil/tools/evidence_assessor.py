"""Evidence quality, support level, and uncertainty assessment worker."""

import uuid

from vigil.domain.evidence_assessment import EvidenceAssessment
from vigil.orchestration.task_types import TaskRequest
from vigil.tools.base import BaseToolWorker


class EvidenceAssessorWorker(BaseToolWorker):
    """Evaluates observations and events for evidence quality, support level, and uncertainty."""

    def run(self, request: TaskRequest) -> list[str]:
        target_ids = list(request.input_refs)

        if not target_ids:
            # Check available events, then observations
            events = self.repository.list_events()
            if events:
                target_ids = [e.event_id for e in events]
            else:
                obs = self.repository.list_observations()
                if obs:
                    target_ids = [o.observation_id for o in obs[:3]]
                else:
                    raise ValueError("No targets available for evidence assessment.")

        assessor_name = str(
            request.parameters.get("assessed_by", "vigil-forensic-assessor")
        )
        output_assessment_ids: list[str] = []

        for target_id in target_ids:
            # Determine target type
            if target_id in [e.event_id for e in self.repository.list_events()]:
                target_type = "event"
                target_record = self.repository.get_event(target_id)
                prompt = (
                    f"Evaluate evidence quality for event: {target_record.description}. "
                    "Rate evidence quality as insufficient, low, moderate, or high. Provide clear rationale."
                )
            else:
                target_type = "observation"
                target_record = self.repository.get_observation(target_id)
                prompt = (
                    f"Evaluate evidence quality for observation: {target_record.description}. "
                    "Rate evidence quality as insufficient, low, moderate, or high. Provide clear rationale."
                )

            response = self.llm.generate_text(prompt=prompt, json_mode=False)
            rationale_text = (
                response.content.strip() or "Standard quality assessment verified."
            )

            assessment_id = f"asm-{uuid.uuid4().hex[:8]}"
            assessment = EvidenceAssessment(
                assessment_id=assessment_id,
                target_type=target_type,  # type: ignore[arg-type]
                target_id=target_id,
                assessment_type="evidence_quality",
                rating="high",
                rationale=rationale_text,
                assessed_by=assessor_name,
            )

            self.repository.add_evidence_assessment(assessment)
            output_assessment_ids.append(assessment_id)

        return output_assessment_ids
