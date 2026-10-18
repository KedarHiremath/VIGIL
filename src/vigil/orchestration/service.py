"""Service coordinating task execution and investigation state."""

from dataclasses import dataclass
from datetime import UTC, datetime

from vigil.orchestration.executor import (
    TaskExecutor,
    TaskResultContractError,
    UnknownTaskTypeError,
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
        if state.status != InvestigationStatus.CREATED:
            raise InvalidInvestigationStateError(
                "A new task can only start from a CREATED investigation."
            )

        if request.task_id in state.task_ids:
            raise DuplicateTaskError(
                f"Task '{request.task_id}' is already recorded in this investigation."
            )

        started_at = datetime.now(UTC)
        running_state = transition_state(
            state,
            InvestigationStatus.RUNNING,
        )

        try:
            task_result = self._executor.execute(request)
        except (UnknownTaskTypeError, TaskResultContractError):
            # Configuration and contract violations are not task failures.
            raise
        except Exception:
            # Convert unexpected worker exceptions into the existing contract.
            finished_at = datetime.now(UTC)
            task_result = TaskResult(
                task_id=request.task_id,
                status=TaskStatus.FAILED,
                output_refs=[],
                error=ErrorDetail(
                    code="WORKER_EXECUTION_ERROR",
                    message="The worker raised an unexpected exception.",
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

        if task_result.status == TaskStatus.COMPLETED:
            updated_state = transition_state(
                state_after_execution,
                InvestigationStatus.COMPLETED,
            )
        elif task_result.status == TaskStatus.FAILED:
            updated_state = transition_state(
                state_after_execution,
                InvestigationStatus.FAILED,
            )
        else:
            # PARTIAL means this task finished partially, not that the
            # overall investigation has completed.
            updated_state = state_after_execution

        return TaskExecutionOutcome(
            state=updated_state,
            task_result=task_result,
        )
