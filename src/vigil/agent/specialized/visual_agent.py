"""Visual Agent specializing in frame sampling, object/person detection, and scene analysis."""

import uuid
from typing import Any

from vigil.models.base import BaseLLMClient
from vigil.orchestration.investigation_state import InvestigationState
from vigil.orchestration.service import OrchestrationService, TaskExecutionOutcome
from vigil.orchestration.task_types import TaskRequest
from vigil.storage.repository import InvestigationRepository


class VisualAgent:
    """Specialized agent responsible for extracting and visually analyzing footage."""

    def __init__(
        self,
        repository: InvestigationRepository,
        service: OrchestrationService,
        llm_client: BaseLLMClient | None = None,
    ) -> None:
        self.repository = repository
        self.service = service
        self.llm = llm_client

    def extract_frames(
        self,
        state: InvestigationState,
        media_asset_ids: list[str],
        sample_interval_seconds: float = 2.0,
        max_frames: int = 10,
    ) -> TaskExecutionOutcome:
        """Sample frames from media assets to generate Artifact records."""
        task_id = f"task-frame-sampling-{uuid.uuid4().hex[:6]}"
        request = TaskRequest(
            task_id=task_id,
            task_type="frame_sampling",
            input_refs=media_asset_ids,
            parameters={
                "sample_interval_seconds": sample_interval_seconds,
                "max_frames": max_frames,
            },
            requested_by="visual-agent",
        )
        return self.service.execute_task(state=state, request=request)

    def analyze_frames(
        self,
        state: InvestigationState,
        artifact_ids: list[str],
        parameters: dict[str, Any] | None = None,
    ) -> TaskExecutionOutcome:
        """Analyze image artifacts using vision models to detect persons, vehicles, and objects."""
        task_id = f"task-visual-analysis-{uuid.uuid4().hex[:6]}"
        request = TaskRequest(
            task_id=task_id,
            task_type="visual_analysis",
            input_refs=artifact_ids,
            parameters=parameters or {"detect_entities": True},
            requested_by="visual-agent",
        )
        return self.service.execute_task(state=state, request=request)
