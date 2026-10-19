"""Forensic report generator worker synthesizing investigation findings."""

import uuid

from vigil.domain.report import Report
from vigil.orchestration.task_types import TaskRequest
from vigil.storage.repository import EntityNotFoundError
from vigil.tools.base import BaseToolWorker


class ReportGeneratorWorker(BaseToolWorker):
    """Compiles observations, events, assessments, and coverage into a structured Report."""

    def run(self, request: TaskRequest) -> list[str]:
        investigation_id = str(
            request.parameters.get("investigation_id", "inv-default")
        )
        title = str(
            request.parameters.get(
                "title", f"Forensic Investigation Report - {investigation_id}"
            )
        )

        # Retrieve investigation details if available
        try:
            inv = self.repository.get_investigation(investigation_id)
            objective = inv.objective
        except EntityNotFoundError:
            objective = "Forensic timeline and activity verification."

        # Collect references
        observations = self.repository.list_observations()
        obs_ids = [o.observation_id for o in observations]

        events = self.repository.list_events()
        event_ids = [e.event_id for e in events]

        assessments = self.repository.list_evidence_assessments()
        assessment_ids = [a.assessment_id for a in assessments]

        coverages = self.repository.list_coverage_records(investigation_id)
        coverage_ids = [c.coverage_id for c in coverages]

        # Generate summary using LLM
        prompt = (
            f"Generate a formal forensic investigation summary for objective: '{objective}'.\n"
            f"Observations count: {len(obs_ids)}, Events count: {len(event_ids)}, "
            f"Evidence assessments count: {len(assessment_ids)}, Coverage records count: {len(coverage_ids)}.\n"
            "Summarize the findings concisely, maintaining objectivity and evidence linkage."
        )

        response = self.llm.generate_text(prompt=prompt, json_mode=False)
        summary = (
            response.content.strip()
            or f"Investigation {investigation_id} completed with {len(obs_ids)} observations and {len(event_ids)} verified events."
        )

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
                request.parameters.get("generated_by", "vigil-forensic-agent")
            ),
        )

        self.repository.add_report(report)
        return [report_id]
