"""Lifecycle transitions for investigation state."""

from datetime import UTC, datetime

from vigil.orchestration.investigation_state import (
    InvestigationState,
    InvestigationStatus,
)


class InvalidStateTransitionError(ValueError):
    """Raised when an investigation transition is not allowed."""


_ALLOWED_TRANSITIONS: dict[InvestigationStatus, frozenset[InvestigationStatus]] = {
    InvestigationStatus.CREATED: frozenset(
        {
            InvestigationStatus.RUNNING,
            InvestigationStatus.FAILED,
        }
    ),
    InvestigationStatus.RUNNING: frozenset(
        {
            InvestigationStatus.PAUSED,
            InvestigationStatus.COMPLETED,
            InvestigationStatus.FAILED,
        }
    ),
    InvestigationStatus.PAUSED: frozenset(
        {
            InvestigationStatus.RUNNING,
            InvestigationStatus.FAILED,
        }
    ),
    InvestigationStatus.COMPLETED: frozenset(),
    InvestigationStatus.FAILED: frozenset(),
}


def transition_state(
    state: InvestigationState,
    new_status: InvestigationStatus,
) -> InvestigationState:
    """Return a new state with a validated lifecycle transition."""
    if new_status not in _ALLOWED_TRANSITIONS[state.status]:
        raise InvalidStateTransitionError(
            f"Cannot transition investigation from "
            f"'{state.status.value}' to '{new_status.value}'."
        )

    now = datetime.now(UTC)

    updates: dict[str, object] = {
        "status": new_status,
        "updated_at": now,
    }

    if new_status == InvestigationStatus.RUNNING and state.started_at is None:
        updates["started_at"] = now

    if new_status in {
        InvestigationStatus.COMPLETED,
        InvestigationStatus.FAILED,
    }:
        updates["completed_at"] = now

    # Revalidate through Pydantic instead of using model_copy(update=...),
    # which does not validate updated values by default.
    return InvestigationState.model_validate(state.model_dump() | updates)
