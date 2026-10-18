"""Tests for synchronous task execution."""

import pytest

from vigil.orchestration.executor import (
    TaskExecutor,
    TaskResultContractError,
    UnknownTaskTypeError,
)
from vigil.orchestration.task_types import (
    ErrorDetail,
    TaskRequest,
    TaskResult,
    TaskStatus,
)


def make_request(
    task_id: str = "task-001",
    task_type: str = "demo",
) -> TaskRequest:
    """Build a valid request for executor tests."""
    return TaskRequest(
        task_id=task_id,
        task_type=task_type,
        input_refs=[],
        parameters={},
    )


def make_result(
    task_id: str = "task-001",
    status: TaskStatus = TaskStatus.COMPLETED,
) -> TaskResult:
    """Build a valid result for executor tests."""
    error = (
        ErrorDetail(
            code="TEST_ERROR",
            message="Simulated task failure",
            retryable=False,
        )
        if status == TaskStatus.FAILED
        else None
    )

    return TaskResult(
        task_id=task_id,
        status=status,
        output_refs=[],
        error=error,
    )


class FakeWorker:
    """A deterministic worker used only in tests."""

    def __init__(self, result: object | None = None) -> None:
        self.result = result
        self.received_request: TaskRequest | None = None

    def execute(self, request: TaskRequest) -> TaskResult:
        self.received_request = request

        if self.result is None:
            return make_result(task_id=request.task_id)

        return self.result  # type: ignore[return-value]


def test_executor_routes_request_to_registered_worker() -> None:
    executor = TaskExecutor()
    worker = FakeWorker()
    executor.register("demo", worker)
    request = make_request()

    result = executor.execute(request)

    assert result.task_id == request.task_id
    assert result.status == TaskStatus.COMPLETED
    assert worker.received_request is request


def test_executor_rejects_unknown_task_type() -> None:
    executor = TaskExecutor()

    with pytest.raises(UnknownTaskTypeError):
        executor.execute(make_request())


def test_executor_rejects_duplicate_registration() -> None:
    executor = TaskExecutor()
    executor.register("demo", FakeWorker())

    with pytest.raises(ValueError, match="already registered"):
        executor.register("demo", FakeWorker())


def test_executor_rejects_blank_task_type_registration() -> None:
    executor = TaskExecutor()

    with pytest.raises(ValueError, match="must not be blank"):
        executor.register("   ", FakeWorker())


def test_executor_rejects_mismatched_result_task_id() -> None:
    executor = TaskExecutor()
    executor.register("demo", FakeWorker(make_result("another-task")))

    with pytest.raises(TaskResultContractError, match="task_id"):
        executor.execute(make_request())


def test_executor_rejects_non_task_result() -> None:
    executor = TaskExecutor()
    executor.register("demo", FakeWorker({"status": "completed"}))

    with pytest.raises(TaskResultContractError, match="must return a TaskResult"):
        executor.execute(make_request())


@pytest.mark.parametrize(
    "status",
    [TaskStatus.PENDING, TaskStatus.RUNNING],
)
def test_executor_rejects_non_final_status(
    status: TaskStatus,
) -> None:
    executor = TaskExecutor()
    executor.register("demo", FakeWorker(make_result(status=status)))

    with pytest.raises(TaskResultContractError, match="final task status"):
        executor.execute(make_request())


@pytest.mark.parametrize(
    "status",
    [TaskStatus.COMPLETED, TaskStatus.PARTIAL, TaskStatus.FAILED],
)
def test_executor_accepts_final_statuses(status: TaskStatus) -> None:
    executor = TaskExecutor()
    executor.register("demo", FakeWorker(make_result(status=status)))

    result = executor.execute(make_request())

    assert result.status == status
