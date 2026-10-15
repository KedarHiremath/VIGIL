"""Tests for VIGIL execution and orchestration schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from vigil.orchestration.investigation_state import (
    InvestigationState,
    InvestigationStatus,
)
from vigil.orchestration.task_types import (
    ErrorDetail,
    ModelOutput,
    TaskRequest,
    TaskResult,
    TaskStatus,
)


def test_task_request_accepts_valid_inputs() -> None:
    task = TaskRequest(
        task_id="task_001",
        task_type="visual_analysis",
        input_refs=["media_001"],
        parameters={"start_seconds": 10, "end_seconds": 15},
    )

    assert task.task_type == "visual_analysis"


def test_task_request_rejects_duplicate_input_refs() -> None:
    with pytest.raises(ValidationError):
        TaskRequest(
            task_id="task_001",
            task_type="visual_analysis",
            input_refs=["media_001", "media_001"],
        )


def test_task_request_rejects_naive_timestamp() -> None:
    with pytest.raises(ValidationError):
        TaskRequest(
            task_id="task_001",
            task_type="visual_analysis",
            created_at=datetime(2026, 10, 14, 10, 0),
        )


def test_error_detail_rejects_retry_delay_for_non_retryable_error() -> None:
    with pytest.raises(ValidationError):
        ErrorDetail(
            code="INVALID_INPUT",
            message="The input is invalid.",
            retryable=False,
            retry_after_seconds=5,
        )


def test_error_detail_accepts_retryable_error() -> None:
    error = ErrorDetail(
        code="TEMPORARY_FAILURE",
        message="The service is temporarily unavailable.",
        retryable=True,
        retry_after_seconds=5,
    )

    assert error.retryable is True


def test_failed_task_result_requires_error() -> None:
    with pytest.raises(ValidationError):
        TaskResult(
            task_id="task_001",
            status=TaskStatus.FAILED,
        )


def test_completed_task_result_rejects_error() -> None:
    with pytest.raises(ValidationError):
        TaskResult(
            task_id="task_001",
            status=TaskStatus.COMPLETED,
            error=ErrorDetail(
                code="ERROR",
                message="Unexpected error.",
                retryable=False,
            ),
        )


def test_task_result_rejects_reversed_timestamps() -> None:
    with pytest.raises(ValidationError):
        TaskResult(
            task_id="task_001",
            status=TaskStatus.COMPLETED,
            started_at=datetime(2026, 10, 14, 12, tzinfo=UTC),
            completed_at=datetime(2026, 10, 14, 11, tzinfo=UTC),
        )


def test_model_output_accepts_structured_payload() -> None:
    output = ModelOutput(
        output_id="output_001",
        producer_name="test-vision-model",
        output_type="detection",
        payload={
            "label": "person",
            "bounding_box": [0.1, 0.2, 0.4, 0.8],
        },
        confidence=0.91,
    )

    assert output.payload["label"] == "person"


def test_model_output_rejects_invalid_confidence() -> None:
    with pytest.raises(ValidationError):
        ModelOutput(
            output_id="output_001",
            producer_name="test-model",
            output_type="detection",
            payload={"label": "person"},
            confidence=1.5,
        )


def test_investigation_state_defaults_to_created() -> None:
    state = InvestigationState(
        investigation_id="investigation_001",
    )

    assert state.status == InvestigationStatus.CREATED


def test_investigation_state_rejects_duplicate_task_ids() -> None:
    with pytest.raises(ValidationError):
        InvestigationState(
            investigation_id="investigation_001",
            task_ids=["task_001", "task_001"],
        )


def test_completed_investigation_requires_completion_time() -> None:
    with pytest.raises(ValidationError):
        InvestigationState(
            investigation_id="investigation_001",
            status=InvestigationStatus.COMPLETED,
        )


def test_investigation_state_accepts_completed_workflow() -> None:
    state = InvestigationState(
        investigation_id="investigation_001",
        status=InvestigationStatus.COMPLETED,
        task_ids=["task_001"],
        observation_ids=["obs_001"],
        started_at=datetime(2026, 10, 14, 10, tzinfo=UTC),
        updated_at=datetime(2026, 10, 14, 11, tzinfo=UTC),
        completed_at=datetime(2026, 10, 14, 11, tzinfo=UTC),
    )

    assert state.status == InvestigationStatus.COMPLETED


from datetime import datetime

import pytest
from pydantic import ValidationError

from vigil.domain.common import ConfidenceScore
from vigil.orchestration.investigation_state import (
    InvestigationState,
    InvestigationStatus,
)
from vigil.orchestration.task_types import (
    ModelOutput,
    TaskRequest,
    TaskResult,
    TaskStatus,
)


def test_investigation_state_normalizes_shared_references() -> None:
    state = InvestigationState(
        investigation_id=" inv-001 ",
        task_ids=[" task-001 "],
        observation_ids=[" obs-001 "],
    )

    assert state.investigation_id == "inv-001"
    assert state.task_ids == ["task-001"]
    assert state.observation_ids == ["obs-001"]


def test_investigation_state_rejects_duplicate_ids_after_normalization() -> None:
    with pytest.raises(ValidationError):
        InvestigationState(
            investigation_id="inv-001",
            task_ids=["task-001", " task-001 "],
        )


def test_task_request_rejects_naive_creation_timestamp() -> None:
    with pytest.raises(ValidationError):
        TaskRequest(
            task_id="task-001",
            task_type="frame_sampling",
            created_at=datetime(2026, 10, 15, 9, 0),
        )


def test_task_result_normalizes_task_id_and_output_references() -> None:
    result = TaskResult(
        task_id=" task-001 ",
        status=TaskStatus.COMPLETED,
        output_refs=[" obs-001 "],
    )

    assert result.task_id == "task-001"
    assert result.output_refs == ["obs-001"]


def test_model_output_rejects_non_finite_confidence() -> None:
    with pytest.raises(ValidationError):
        ModelOutput(
            output_id="output-001",
            producer_name="vision-model",
            output_type="detection",
            payload={"label": "person"},
            confidence=float("nan"),
        )


def test_completed_investigation_requires_completion_timestamp() -> None:
    with pytest.raises(ValidationError):
        InvestigationState(
            investigation_id="inv-001",
            status=InvestigationStatus.COMPLETED,
        )
