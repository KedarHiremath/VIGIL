"""Report Writer Agent compiling structured forensic findings into comprehensive reports."""

import uuid
from typing import Any

from vigil.models.base import BaseLLMClient
from vigil.orchestration.investigation_state import InvestigationState
from vigil.orchestration.service import OrchestrationService, TaskExecutionOutcome
from vigil.orchestration.task_types import TaskRequest
from vigil.storage.repository import InvestigationRepository


class ReportWriterAgent:
    """Specialized agent responsible for synthesizing validated evidence into forensic reports."""

    def __init__(
        self,
        repository: InvestigationRepository,
        service: OrchestrationService,
        llm_client: BaseLLMClient | None = None,
    ) -> None:
        self.repository = repository
        self.service = service
        self.llm = llm_client

    def generate_report(
        self,
        state: InvestigationState,
        investigation_id: str,
        title: str | None = None,
        parameters: dict[str, Any] | None = None,
    ) -> TaskExecutionOutcome:
        """Synthesize verified findings into a structured, evidence-grounded Report domain object."""
        task_id = f"task-report-generation-{uuid.uuid4().hex[:6]}"
        params = dict(parameters or {})
        params["investigation_id"] = investigation_id
        if title:
            params["title"] = title
        params.setdefault("generated_by", "report-writer-agent")

        request = TaskRequest(
            task_id=task_id,
            task_type="report_generation",
            input_refs=[],
            parameters=params,
            requested_by="report-writer-agent",
        )
        return self.service.execute_task(state=state, request=request)
