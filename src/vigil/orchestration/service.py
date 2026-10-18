"""Service coordinating task execution and investigation state."""

from dataclasses import dataclass
from datetime import UTC, datetime

from vigil.orchestration.executor import (
    TaskExecutor,
    TaskResultContractError,
    UnknownTaskTypeError,
    WorkerExecutionError,
)
from vigil.orchestration.investigation_state import (
    InvestigationState,
    InvestigationStatus,
)
from vigil.orchestration.task_types import (
    ErrorDetail,
    TaskRequest,
    TaskResult,
    TaskStatus,
)
from vigil.orchestration.transitions import (
    transition_state,
)


@dataclass(frozen=True, slots=True)
class TaskExecutionOutcome:
    """Outcome of executing one task within an investigation."""

    state: InvestigationState
    task_result: TaskResult


class OrchestrationServiceError(RuntimeError):
    """Base exception for orchestration service errors."""


class InvalidInvestigationStateError(OrchestrationServiceError):
    """Raised when the investigation cannot accept a new task."""


class DuplicateTaskError(OrchestrationServiceError):
    """Raised when a task ID already exists in the investigation state."""


class OrchestrationService:
    """Coordinate one synchronous task execution."""

    def __init__(self, executor: TaskExecutor) -> None:
        self._executor = executor

    def execute_task(
        self,
        state: InvestigationState,
        request: TaskRequest,
    ) -> TaskExecutionOutcome:
        """Execute one task and return its result and updated state."""
        if state.status not in {
            InvestigationStatus.CREATED,
            InvestigationStatus.RUNNING,
        }:
            raise InvalidInvestigationStateError(
                "Tasks can only run in CREATED or RUNNING investigations."
            )

        if request.task_id in state.task_ids:
            raise DuplicateTaskError(
                f"Task '{request.task_id}' is already recorded in this investigation."
            )

        started_at = datetime.now(UTC)

        if state.status == InvestigationStatus.CREATED:
            running_state = transition_state(
                state,
                InvestigationStatus.RUNNING,
            )
        else:
            running_state = state

        try:
            task_result = self._executor.execute(request)
        except (UnknownTaskTypeError, TaskResultContractError):
            # Configuration and contract violations must remain visible.
            raise
        except WorkerExecutionError:
            # Convert an explicitly reported worker failure into TaskResult.
            finished_at = datetime.now(UTC)
            task_result = TaskResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                output_refs=[],
                error=ErrorDetail(
                    code="WORKER_EXECUTION_ERROR",
                    message="The worker reported an execution failure.",
                    retryable=False,
                ),
                started_at=started_at,
                completed_at=finished_at,
            )

        finished_at = datetime.now(UTC)

        # Add the task ID to a new immutable state.
        state_after_execution = InvestigationState.model_validate(
            running_state.model_dump()
            | {
                "task_ids": [*running_state.task_ids, request.task_id],
                "updated_at": finished_at,
            }
        )

        if task_result.status == TaskStatus.FAILED:
            updated_state = transition_state(
                state_after_execution,
                InvestigationStatus.FAILED,
            )
        else:
            # A completed or partial task does not complete the investigation.
            updated_state = state_after_execution

        return TaskExecutionOutcome(
            state=updated_state,
            task_result=task_result,
        )

    def complete_investigation(
        self,
        state: InvestigationState,
    ) -> InvestigationState:
        """Mark a running investigation as completed."""
        if state.status != InvestigationStatus.RUNNING:
            raise InvalidInvestigationStateError(
                "Only a RUNNING investigation can be completed."
            )

        return transition_state(
            state,
            InvestigationStatus.COMPLETED,
        )
