"""Temporal & Correlation Agent relating multi-modal observations into chronological events."""

import uuid
from typing import Any

from vigil.models.base import BaseLLMClient
from vigil.orchestration.investigation_state import InvestigationState
from vigil.orchestration.service import OrchestrationService, TaskExecutionOutcome
from vigil.orchestration.task_types import TaskRequest
from vigil.storage.repository import InvestigationRepository


class TemporalCorrelationAgent:
    """Specialized agent responsible for synthesizing timeline sequences and event links."""

    def __init__(
        self,
        repository: InvestigationRepository,
        service: OrchestrationService,
        llm_client: BaseLLMClient | None = None,
    ) -> None:
        self.repository = repository
        self.service = service
        self.llm = llm_client

    def correlate(
        self,
        state: InvestigationState,
        observation_ids: list[str],
        parameters: dict[str, Any] | None = None,
    ) -> TaskExecutionOutcome:
        """Combine observations across video and audio timelines into Events and EventLinks."""
        task_id = f"task-event-correlation-{uuid.uuid4().hex[:6]}"
        request = TaskRequest(
            task_id=task_id,
            task_type="event_correlation",
            input_refs=observation_ids,
            parameters=parameters or {},
            requested_by="temporal-correlation-agent",
        )
        return self.service.execute_task(state=state, request=request)
