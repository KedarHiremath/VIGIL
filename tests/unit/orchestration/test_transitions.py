"""Tests for investigation state transitions."""

from datetime import UTC, datetime

import pytest

from vigil.orchestration.investigation_state import (
    InvestigationState,
    InvestigationStatus,
)
from vigil.orchestration.transitions import (
    InvalidStateTransitionError,
    transition_state,
)


def make_state() -> InvestigationState:
    """Create an initial investigation state."""
    return InvestigationState(investigation_id="inv-001")


def test_created_investigation_can_start() -> None:
    original = make_state()

    updated = transition_state(
        original,
        InvestigationStatus.RUNNING,
    )

    assert updated.status == InvestigationStatus.RUNNING
    assert updated.started_at is not None
    assert updated.completed_at is None
    assert updated.updated_at >= updated.started_at
    assert original.status == InvestigationStatus.CREATED
    assert original.started_at is None


def test_running_investigation_can_pause() -> None:
    running = transition_state(
        make_state(),
        InvestigationStatus.RUNNING,
    )

    paused = transition_state(
        running,
        InvestigationStatus.PAUSED,
    )

    assert paused.status == InvestigationStatus.PAUSED
    assert paused.started_at == running.started_at
    assert paused.completed_at is None


def test_paused_investigation_can_resume() -> None:
    running = transition_state(
        make_state(),
        InvestigationStatus.RUNNING,
    )
    paused = transition_state(
        running,
        InvestigationStatus.PAUSED,
    )

    resumed = transition_state(
        paused,
        InvestigationStatus.RUNNING,
    )

    assert resumed.status == InvestigationStatus.RUNNING
    assert resumed.started_at == running.started_at
    assert resumed.completed_at is None


@pytest.mark.parametrize(
    "terminal_status",
    [
        InvestigationStatus.COMPLETED,
        InvestigationStatus.FAILED,
    ],
)
def test_running_investigation_can_reach_terminal_status(
    terminal_status: InvestigationStatus,
) -> None:
    running = transition_state(
        make_state(),
        InvestigationStatus.RUNNING,
    )

    terminal = transition_state(running, terminal_status)

    assert terminal.status == terminal_status
    assert terminal.completed_at is not None
    assert terminal.completed_at >= terminal.started_at


def test_created_investigation_can_fail() -> None:
    failed = transition_state(
        make_state(),
        InvestigationStatus.FAILED,
    )

    assert failed.status == InvestigationStatus.FAILED
    assert failed.completed_at is not None
    assert failed.started_at is None


def test_paused_investigation_can_fail() -> None:
    running = transition_state(
        make_state(),
        InvestigationStatus.RUNNING,
    )
    paused = transition_state(
        running,
        InvestigationStatus.PAUSED,
    )

    failed = transition_state(
        paused,
        InvestigationStatus.FAILED,
    )

    assert failed.status == InvestigationStatus.FAILED
    assert failed.started_at == running.started_at
    assert failed.completed_at is not None


@pytest.mark.parametrize(
    ("initial_status", "target_status"),
    [
        (InvestigationStatus.CREATED, InvestigationStatus.PAUSED),
        (InvestigationStatus.RUNNING, InvestigationStatus.CREATED),
        (InvestigationStatus.PAUSED, InvestigationStatus.COMPLETED),
        (InvestigationStatus.COMPLETED, InvestigationStatus.RUNNING),
        (InvestigationStatus.FAILED, InvestigationStatus.RUNNING),
    ],
)
def test_invalid_transition_is_rejected(
    initial_status: InvestigationStatus,
    target_status: InvestigationStatus,
) -> None:
    state_data: dict[str, object] = {
        "investigation_id": "inv-001",
        "status": initial_status,
    }

    # The existing schema requires completion timestamps for terminal states.
    if initial_status in {
        InvestigationStatus.COMPLETED,
        InvestigationStatus.FAILED,
    }:
        state_data["completed_at"] = datetime.now(UTC)

    state = InvestigationState.model_validate(state_data)

    with pytest.raises(InvalidStateTransitionError):
        transition_state(state, target_status)


def test_transition_does_not_mutate_original_state() -> None:
    original = make_state()

    transition_state(original, InvestigationStatus.RUNNING)

    assert original.status == InvestigationStatus.CREATED
    assert original.started_at is None
