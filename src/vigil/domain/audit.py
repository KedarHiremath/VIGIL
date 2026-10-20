"""Audit log schema for tracking investigator review decisions and provenance."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from vigil.domain.base import DomainModel
from vigil.domain.common import Identifier, Timestamp


class AuditLog(DomainModel):
    """Immutable record tracking human review decisions and lifecycle modifications."""

    audit_id: Identifier = Field(
        description="Unique identifier for this audit entry.",
    )

    investigation_id: Identifier = Field(
        description="ID of the investigation associated with this audit entry.",
    )

    action: Literal[
        "event_review",
        "event_edit",
        "report_finalize",
        "report_regenerate",
        "investigation_update",
    ] | str = Field(
        description="Action performed (e.g. event_review, report_finalize).",
    )

    actor: str = Field(
        min_length=1,
        description="Investigator badge, username, or agent ID who executed the action.",
    )

    timestamp: Timestamp = Field(
        default_factory=lambda: datetime.now(UTC),
        description="Timezone-aware timestamp when the action occurred.",
    )

    target_type: Literal["event", "report", "investigation", "artifact"] = Field(
        description="Domain entity type targeted by the action.",
    )

    target_id: Identifier = Field(
        description="Identifier of the targeted domain record.",
    )

    changes: dict[str, Any] = Field(
        default_factory=dict,
        description="Dictionary detailing previous and updated values.",
    )

    notes: str | None = Field(
        default=None,
        description="Investigator rationale, remarks, or justification.",
    )

    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional forensic context or parameter metadata.",
    )

    @field_validator("actor")
    @classmethod
    def reject_blank_actor(cls, value: str) -> str:
        """Reject blank actor identifiers."""
        if not value.strip():
            raise ValueError("Actor must not be blank")
        return value.strip()
