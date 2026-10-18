"""Tests for the orchestration service."""

import pytest

from vigil.orchestration.executor import (
    TaskExecutor,
    TaskResultContractError,
    UnknownTaskTypeError,
)
from vigil.orchestration.investigation_state import (
    InvestigationState,
    InvestigationStatus,
)
from vigil.orchestration.service import (
    DuplicateTaskError,
    InvalidInvestigationStateError,
    OrchestrationService,
)
from vigil.orchestration.task_types import (
    ErrorDetail,
    TaskRequest,
    TaskResult,
    TaskStatus,
)
from vigil.orchestration.transitions import transition_state


def make_request(
    task_id: str = "task-001",
    task_type: str = "demo",
) -> TaskRequest:
    """Build a valid task request."""
    return TaskRequest(
        task_id=task_id,
        task_type=task_type,
        input_refs=[],
        parameters={},
    )


def make_state() -> InvestigationState:
    """Build a new investigation state."""
    return InvestigationState(investigation_id="inv-001")


def make_result(
    task_id: str = "task-001",
    status: TaskStatus = TaskStatus.COMPLETED,
) -> TaskResult:
    """Build a valid task result."""
    error = (
        ErrorDetail(
            code="TEST_ERROR",
            message="Simulated task failure.",
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
    """Worker returning a predetermined result."""

    def __init__(self, result: TaskResult) -> None:
        self.result = result
        self.calls = 0

    def execute(self, request: TaskRequest) -> TaskResult:
        self.calls += 1
        return self.result


class RaisingWorker:
    """Worker simulating an unexpected execution exception."""

    def execute(self, request: TaskRequest) -> TaskResult:
        raise RuntimeError("Simulated internal worker error")


def make_service(worker: object) -> OrchestrationService:
    """Build a service with one registered demo worker."""
    executor = TaskExecutor()
    executor.register("demo", worker)
    return OrchestrationService(executor)


def test_completed_task_completes_investigation() -> None:
    worker = FakeWorker(make_result())
    service = make_service(worker)
    original = make_state()

    outcome = service.execute_task(original, make_request())

    assert outcome.task_result.status == TaskStatus.COMPLETED
    assert outcome.state.status == InvestigationStatus.COMPLETED
    assert outcome.state.task_ids == ["task-001"]
    assert outcome.state.started_at is not None
    assert outcome.state.completed_at is not None
    assert original.status == InvestigationStatus.CREATED
    assert original.task_ids == []
    assert worker.calls == 1


def test_partial_task_keeps_investigation_running() -> None:
    worker = FakeWorker(make_result(status=TaskStatus.PARTIAL))
    service = make_service(worker)

    outcome = service.execute_task(make_state(), make_request())

    assert outcome.task_result.status == TaskStatus.PARTIAL
    assert outcome.state.status == InvestigationStatus.RUNNING
    assert outcome.state.task_ids == ["task-001"]
    assert outcome.state.completed_at is None


def test_failed_task_fails_investigation() -> None:
    worker = FakeWorker(make_result(status=TaskStatus.FAILED))
    service = make_service(worker)

    outcome = service.execute_task(make_state(), make_request())

    assert outcome.task_result.status == TaskStatus.FAILED
    assert outcome.task_result.error is not None
    assert outcome.state.status == InvestigationStatus.FAILED
    assert outcome.state.task_ids == ["task-001"]
    assert outcome.state.completed_at is not None


def test_unexpected_worker_exception_becomes_failed_result() -> None:
    service = make_service(RaisingWorker())

    outcome = service.execute_task(make_state(), make_request())

    assert outcome.task_result.status == TaskStatus.FAILED
    assert outcome.task_result.error is not None
    assert outcome.task_result.error.code == "WORKER_EXECUTION_ERROR"
    assert outcome.task_result.started_at is not None
    assert outcome.task_result.completed_at is not None
    assert outcome.state.status == InvestigationStatus.FAILED


def test_unknown_task_type_propagates() -> None:
    service = OrchestrationService(TaskExecutor())

    with pytest.raises(UnknownTaskTypeError):
        service.execute_task(make_state(), make_request())


def test_worker_result_contract_violation_propagates() -> None:
    worker = FakeWorker(make_result(task_id="another-task"))
    service = make_service(worker)

    with pytest.raises(TaskResultContractError):
        service.execute_task(make_state(), make_request())


def test_duplicate_task_id_is_rejected_before_execution() -> None:
    worker = FakeWorker(make_result())
    service = make_service(worker)
    state = make_state().model_copy(update={"task_ids": ["task-001"]})

    with pytest.raises(DuplicateTaskError):
        service.execute_task(state, make_request())

    assert worker.calls == 0


def test_non_created_investigation_is_rejected() -> None:
    worker = FakeWorker(make_result())
    service = make_service(worker)
    running_state = transition_state(
        make_state(),
        InvestigationStatus.RUNNING,
    )

    with pytest.raises(InvalidInvestigationStateError):
        service.execute_task(running_state, make_request())

    assert worker.calls == 0
