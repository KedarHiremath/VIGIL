"""Agentic Orchestrator and Lead Investigator coordinating multi-phase video forensics."""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from vigil.agent.planner import InvestigationPlanner
from vigil.agent.registry import create_default_executor
from vigil.agent.specialized.audio_agent import AudioAgent
from vigil.agent.specialized.correlation_agent import TemporalCorrelationAgent
from vigil.agent.specialized.report_writer_agent import ReportWriterAgent
from vigil.agent.specialized.verification_agent import EvidenceVerificationAgent
from vigil.agent.specialized.visual_agent import VisualAgent
from vigil.domain.coverage import CoverageRecord
from vigil.domain.event import Event
from vigil.domain.evidence_assessment import EvidenceAssessment
from vigil.domain.investigation import Investigation
from vigil.domain.observation import Observation
from vigil.domain.report import Report
from vigil.models.base import BaseLLMClient
from vigil.models.factory import get_llm_client
from vigil.orchestration.investigation_state import (
    InvestigationState,
    InvestigationStatus,
)
from vigil.orchestration.service import OrchestrationService, TaskExecutionOutcome
from vigil.orchestration.task_types import TaskRequest, TaskResult, TaskStatus
from vigil.storage.repository import InvestigationRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InvestigationOutcome:
    """Consolidated outcome of an end-to-end agentic forensic investigation."""

    investigation: Investigation
    state: InvestigationState
    report: Report | None
    task_results: list[TaskResult] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    assessments: list[EvidenceAssessment] = field(default_factory=list)
    coverage_records: list[CoverageRecord] = field(default_factory=list)


class AgenticOrchestrator:
    """Orchestrator that coordinates specialized agents across the full forensic lifecycle."""

    def __init__(
        self,
        repository: InvestigationRepository | None = None,
        service: OrchestrationService | None = None,
        planner: InvestigationPlanner | None = None,
        llm_client: BaseLLMClient | None = None,
    ) -> None:
        self.repository = repository or InvestigationRepository()
        self.llm = llm_client or get_llm_client()
        self.planner = planner or InvestigationPlanner(llm_client=self.llm)

        if service is None:
            executor = create_default_executor(
                repository=self.repository, llm_client=self.llm
            )
            self.service = OrchestrationService(executor=executor)
        else:
            self.service = service

        # Instantiate specialized agents
        self.visual_agent = VisualAgent(
            repository=self.repository,
            service=self.service,
            llm_client=self.llm,
        )
        self.audio_agent = AudioAgent(
            repository=self.repository,
            service=self.service,
            llm_client=self.llm,
        )
        self.correlation_agent = TemporalCorrelationAgent(
            repository=self.repository,
            service=self.service,
            llm_client=self.llm,
        )
        self.verification_agent = EvidenceVerificationAgent(
            repository=self.repository,
            service=self.service,
            llm_client=self.llm,
        )
        self.report_writer = ReportWriterAgent(
            repository=self.repository,
            service=self.service,
            llm_client=self.llm,
        )

    def step(
        self,
        state: InvestigationState,
        request: TaskRequest,
    ) -> TaskExecutionOutcome:
        """Execute one forensic task step and synchronize state and repository."""
        outcome = self.service.execute_task(state=state, request=request)

        # Sync output IDs into state
        current_obs_ids = set(outcome.state.observation_ids)
        current_evt_ids = set(outcome.state.event_ids)

        new_obs_ids = [
            ref
            for ref in outcome.task_result.output_refs
            if ref.startswith("obs-")
        ]
        new_evt_ids = [
            ref
            for ref in outcome.task_result.output_refs
            if ref.startswith("evt-")
        ]

        updated_obs = list(current_obs_ids | set(new_obs_ids))
        updated_evts = list(current_evt_ids | set(new_evt_ids))

        synced_state = InvestigationState.model_validate(
            outcome.state.model_dump()
            | {
                "observation_ids": updated_obs,
                "event_ids": updated_evts,
                "updated_at": datetime.now(UTC),
            }
        )

        self.repository.save_state(synced_state)
        return TaskExecutionOutcome(
            state=synced_state, task_result=outcome.task_result
        )

    def run_investigation(
        self,
        investigation: Investigation,
    ) -> InvestigationOutcome:
        """Run the full autonomous agentic forensic investigation loop."""
        # Save investigation in repository
        self.repository.add_investigation(investigation)

        # Initialize investigation state
        state = InvestigationState(
            investigation_id=investigation.investigation_id,
            status=InvestigationStatus.CREATED,
        )
        self.repository.save_state(state)

        # Generate investigation plan
        planned_tasks = self.planner.plan_investigation(investigation)
        task_results: list[TaskResult] = []

        # Execute each planned task through the orchestration service
        for planned in planned_tasks:
            task_req = planned.to_task_request(
                requested_by=investigation.created_by
                or "lead-investigator"
            )

            # Execute step
            outcome = self.step(state, task_req)
            state = outcome.state
            task_results.append(outcome.task_result)

            # If task failed, stop the investigation pipeline
            if outcome.task_result.status == TaskStatus.FAILED:
                logger.error(
                    f"Investigation task {task_req.task_id} failed: "
                    f"{outcome.task_result.error}"
                )
                break

        # If all tasks succeeded or yielded partial results, complete the investigation
        final_report: Report | None = None
        if state.status == InvestigationStatus.RUNNING:
            state = self.service.complete_investigation(state)
            self.repository.save_state(state)

            reports = self.repository.list_reports(
                investigation.investigation_id
            )
            if reports:
                final_report = reports[-1]

        # Collect consolidated findings
        return InvestigationOutcome(
            investigation=investigation,
            state=state,
            report=final_report,
            task_results=task_results,
            observations=self.repository.list_observations(
                state.observation_ids
            ),
            events=self.repository.list_events(state.event_ids),
            assessments=self.repository.list_evidence_assessments(),
            coverage_records=self.repository.list_coverage_records(
                investigation.investigation_id
            ),
        )


# Backward-compatible alias
LeadInvestigatorAgent = AgenticOrchestrator
