"""Agentic Orchestrator and Lead Investigator coordinating multi-phase video forensics."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

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
        self._custom_service = service
        self.llm = llm_client or get_llm_client()

    @property
    def llm(self) -> BaseLLMClient:
        return self._llm

    @llm.setter
    def llm(self, client: BaseLLMClient) -> None:
        self._llm = client
        self.planner = InvestigationPlanner(llm_client=self._llm)
        if self._custom_service is None:
            executor = create_default_executor(
                repository=self.repository, llm_client=self._llm
            )
            self.service = OrchestrationService(executor=executor)
        else:
            self.service = self._custom_service

        self.visual_agent = VisualAgent(
            repository=self.repository,
            service=self.service,
            llm_client=self._llm,
        )
        self.audio_agent = AudioAgent(
            repository=self.repository,
            service=self.service,
            llm_client=self._llm,
        )
        self.correlation_agent = TemporalCorrelationAgent(
            repository=self.repository,
            service=self.service,
            llm_client=self._llm,
        )
        self.verification_agent = EvidenceVerificationAgent(
            repository=self.repository,
            service=self.service,
            llm_client=self._llm,
        )
        self.report_writer = ReportWriterAgent(
            repository=self.repository,
            service=self.service,
            llm_client=self._llm,
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
        event_callback: Callable[[str, dict[str, Any]], None] | None = None,
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
        if event_callback:
            event_callback(
                "state_changed",
                {
                    "investigation_id": investigation.investigation_id,
                    "status": state.status.value,
                    "updated_at": state.updated_at.isoformat(),
                },
            )

        # Generate investigation plan
        planned_tasks = self.planner.plan_investigation(investigation)
        if event_callback:
            event_callback(
                "plan_created",
                {
                    "investigation_id": investigation.investigation_id,
                    "task_count": len(planned_tasks),
                    "tasks": [
                        {
                            "task_type": t.task_type,
                            "description": t.description,
                        }
                        for t in planned_tasks
                    ],
                },
            )
        task_results: list[TaskResult] = []

        # Execute each planned task through the orchestration service
        for planned in planned_tasks:
            task_req = planned.to_task_request(
                requested_by=investigation.created_by
                or "lead-investigator"
            )

            if event_callback:
                event_callback(
                    "task_started",
                    {
                        "investigation_id": investigation.investigation_id,
                        "task_id": task_req.task_id,
                        "task_type": task_req.task_type,
                        "description": planned.description,
                    },
                )

            prev_obs_ids = set(state.observation_ids)
            prev_evt_ids = set(state.event_ids)

            # Execute step
            outcome = self.step(state, task_req)
            state = outcome.state
            task_results.append(outcome.task_result)

            if event_callback:
                # Report new observations
                new_obs_ids = set(state.observation_ids) - prev_obs_ids
                if new_obs_ids:
                    new_obs = self.repository.list_observations(list(new_obs_ids))
                    for obs in new_obs:
                        event_callback(
                            "observation_detected",
                            {
                                "investigation_id": investigation.investigation_id,
                                "task_id": task_req.task_id,
                                "observation": obs.model_dump(mode="json"),
                            },
                        )

                # Report new events
                new_evt_ids = set(state.event_ids) - prev_evt_ids
                if new_evt_ids:
                    new_evts = self.repository.list_events(list(new_evt_ids))
                    for evt in new_evts:
                        event_callback(
                            "event_correlated",
                            {
                                "investigation_id": investigation.investigation_id,
                                "task_id": task_req.task_id,
                                "event": evt.model_dump(mode="json"),
                            },
                        )

                # Report coverage updates
                if task_req.task_type == "coverage_evaluation":
                    cov_records = self.repository.list_coverage_records(
                        investigation.investigation_id
                    )
                    for cov in cov_records:
                        event_callback(
                            "coverage_updated",
                            {
                                "investigation_id": investigation.investigation_id,
                                "task_id": task_req.task_id,
                                "coverage": cov.model_dump(mode="json"),
                            },
                        )

                event_callback(
                    "task_completed",
                    {
                        "investigation_id": investigation.investigation_id,
                        "task_id": task_req.task_id,
                        "task_type": task_req.task_type,
                        "status": outcome.task_result.status.value,
                        "output_refs": outcome.task_result.output_refs,
                        "error": outcome.task_result.error.model_dump(mode="json")
                        if outcome.task_result.error
                        else None,
                    },
                )

            # If task failed, stop the investigation pipeline
            if outcome.task_result.status == TaskStatus.FAILED:
                logger.error(
                    f"Investigation task {task_req.task_id} failed: "
                    f"{outcome.task_result.error}"
                )
                if event_callback:
                    event_callback(
                        "investigation_failed",
                        {
                            "investigation_id": investigation.investigation_id,
                            "failed_task_id": task_req.task_id,
                            "error": outcome.task_result.error.message
                            if outcome.task_result.error
                            else "Task execution failed",
                        },
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

            if event_callback:
                event_callback(
                    "state_changed",
                    {
                        "investigation_id": investigation.investigation_id,
                        "status": state.status.value,
                        "updated_at": state.updated_at.isoformat(),
                    },
                )
                event_callback(
                    "investigation_completed",
                    {
                        "investigation_id": investigation.investigation_id,
                        "status": state.status.value,
                        "report_id": final_report.report_id if final_report else None,
                        "report_title": final_report.title if final_report else None,
                    },
                )

        # Collect consolidated findings scoped strictly to this investigation
        inv_obs = self.repository.list_observations(state.observation_ids)
        inv_events = self.repository.list_events(state.event_ids)
        target_ids = set(state.event_ids) | set(state.observation_ids)
        all_assessments = self.repository.list_evidence_assessments()
        scoped_assessments = [a for a in all_assessments if a.target_id in target_ids]

        return InvestigationOutcome(
            investigation=investigation,
            state=state,
            report=final_report,
            task_results=task_results,
            observations=inv_obs,
            events=inv_events,
            assessments=scoped_assessments,
            coverage_records=self.repository.list_coverage_records(
                investigation.investigation_id
            ),
        )


# Backward-compatible alias
LeadInvestigatorAgent = AgenticOrchestrator
