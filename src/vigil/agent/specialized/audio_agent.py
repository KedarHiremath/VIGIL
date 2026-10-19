"""Audio Agent specializing in acoustic transcription, speech-to-text, and sound event analysis."""

import uuid
from typing import Any

from vigil.models.base import BaseLLMClient
from vigil.orchestration.investigation_state import InvestigationState
from vigil.orchestration.service import OrchestrationService, TaskExecutionOutcome
from vigil.orchestration.task_types import TaskRequest
from vigil.storage.repository import InvestigationRepository


class AudioAgent:
    """Specialized agent responsible for acoustic and speech analysis of footage."""

    def __init__(
        self,
        repository: InvestigationRepository,
        service: OrchestrationService,
        llm_client: BaseLLMClient | None = None,
    ) -> None:
        self.repository = repository
        self.service = service
        self.llm = llm_client

    def analyze_audio(
        self,
        state: InvestigationState,
        media_refs: list[str],
        parameters: dict[str, Any] | None = None,
    ) -> TaskExecutionOutcome:
        """Transcribe speech and identify acoustic triggers (alarms, shouts, sirens)."""
        task_id = f"task-audio-transcription-{uuid.uuid4().hex[:6]}"
        request = TaskRequest(
            task_id=task_id,
            task_type="audio_transcription",
            input_refs=media_refs,
            parameters=parameters or {},
            requested_by="audio-agent",
        )
        return self.service.execute_task(state=state, request=request)
