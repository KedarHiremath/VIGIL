"""Evidence Verification Agent assessing quality, support level, and uncertainty."""

import uuid
from typing import Any

from vigil.models.base import BaseLLMClient
from vigil.orchestration.investigation_state import InvestigationState
from vigil.orchestration.service import OrchestrationService, TaskExecutionOutcome
from vigil.orchestration.task_types import TaskRequest
from vigil.storage.repository import InvestigationRepository


class EvidenceVerificationAgent:
    """Specialized agent assessing evidence sufficiency, rating quality, and evaluating coverage."""

    def __init__(
        self,
        repository: InvestigationRepository,
        service: OrchestrationService,
        llm_client: BaseLLMClient | None = None,
    ) -> None:
        self.repository = repository
        self.service = service
        self.llm = llm_client

    def verify_evidence(
        self,
        state: InvestigationState,
        target_ids: list[str],
        parameters: dict[str, Any] | None = None,
    ) -> TaskExecutionOutcome:
        """Assess evidence quality, support level, and uncertainty for observations or events."""
        task_id = f"task-evidence-assessment-{uuid.uuid4().hex[:6]}"
        request = TaskRequest(
            task_id=task_id,
            task_type="evidence_assessment",
            input_refs=target_ids,
            parameters=parameters or {"assessed_by": "evidence-verification-agent"},
            requested_by="evidence-verification-agent",
        )
        return self.service.execute_task(state=state, request=request)

    def evaluate_coverage(
        self,
        state: InvestigationState,
        investigation_id: str,
        source_ref_ids: list[str],
        parameters: dict[str, Any] | None = None,
    ) -> TaskExecutionOutcome:
        """Evaluate whether footage intervals were thoroughly examined or have gaps."""
        task_id = f"task-coverage-evaluation-{uuid.uuid4().hex[:6]}"
        params = dict(parameters or {})
        params["investigation_id"] = investigation_id

        request = TaskRequest(
            task_id=task_id,
            task_type="coverage_evaluation",
            input_refs=source_ref_ids,
            parameters=params,
            requested_by="evidence-verification-agent",
        )
        return self.service.execute_task(state=state, request=request)
