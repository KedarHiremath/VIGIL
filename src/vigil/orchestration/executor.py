"""Synchronous task execution and worker routing."""

from typing import Protocol

from vigil.orchestration.task_types import (
    TaskRequest,
    TaskResult,
    TaskStatus,
)


class TaskWorker(Protocol):
    """Contract for an object capable of executing a task."""

    def execute(self, request: TaskRequest) -> TaskResult:
        """Execute a task and return its result."""
        ...


class ExecutorError(Exception):
    """Base exception for executor errors."""


class UnknownTaskTypeError(ExecutorError):
    """Raised when no worker is registered for a task type."""


class TaskResultContractError(ExecutorError):
    """Raised when a worker violates the result contract."""


class TaskExecutor:
    """Route task requests to registered workers."""

    def __init__(self) -> None:
        self._workers: dict[str, TaskWorker] = {}

    def register(self, task_type: str, worker: TaskWorker) -> None:
        """Register one worker for a task type."""
        normalized_type = task_type.strip()

        if not normalized_type:
            raise ValueError("task_type must not be blank")

        if normalized_type in self._workers:
            raise ValueError(
                f"A worker is already registered for task type '{normalized_type}'"
            )

        self._workers[normalized_type] = worker

    def execute(self, request: TaskRequest) -> TaskResult:
        """Execute a request using its registered worker."""
        worker = self._workers.get(request.task_type)

        if worker is None:
            raise UnknownTaskTypeError(
                f"No worker registered for task type '{request.task_type}'"
            )

        result = worker.execute(request)

        if not isinstance(result, TaskResult):
            raise TaskResultContractError("Worker must return a TaskResult")

        if result.task_id != request.task_id:
            raise TaskResultContractError(
                "Worker result task_id must match request task_id"
            )

        if result.status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
            raise TaskResultContractError(
                "Synchronous workers must return a final task status"
            )

        return result
