"""Unit tests for audit log storage in memory and SQLite repositories."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from vigil.domain.audit import AuditLog
from vigil.storage.repository import InvestigationRepository
from vigil.storage.sqlite_repository import SqliteInvestigationRepository


def test_in_memory_repository_audit_logging() -> None:
    repo = InvestigationRepository()
    t1 = datetime(2026, 10, 20, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 20, 10, 5, tzinfo=UTC)

    log1 = AuditLog(
        audit_id="audit-001",
        investigation_id="inv-001",
        action="event_review",
        actor="user-alice",
        timestamp=t1,
        target_type="event",
        target_id="evt-001",
        changes={"status": {"old": "proposed", "new": "confirmed"}},
        notes="Verified",
    )
    log2 = AuditLog(
        audit_id="audit-002",
        investigation_id="inv-001",
        action="report_finalize",
        actor="user-bob",
        timestamp=t2,
        target_type="report",
        target_id="rep-001",
        changes={"version": {"old": 1, "new": 2}},
    )

    repo.add_audit_log(log1)
    repo.add_audit_log(log2)

    assert repo.get_audit_log("audit-001").actor == "user-alice"
    assert repo.get_audit_log("audit-002").target_id == "rep-001"

    logs = repo.list_audit_logs("inv-001")
    assert len(logs) == 2
    assert logs[0].audit_id == "audit-001"
    assert logs[1].audit_id == "audit-002"

    target_logs = repo.list_audit_logs("inv-001", target_id="evt-001")
    assert len(target_logs) == 1
    assert target_logs[0].audit_id == "audit-001"


def test_sqlite_repository_audit_logging(tmp_path: Path) -> None:
    db_file = tmp_path / "audit_test.db"
    repo = SqliteInvestigationRepository(db_path=db_file)

    t1 = datetime(2026, 10, 20, 12, 0, tzinfo=UTC)
    t2 = datetime(2026, 10, 20, 12, 10, tzinfo=UTC)

    log1 = AuditLog(
        audit_id="audit-101",
        investigation_id="inv-500",
        action="event_review",
        actor="badge-701",
        timestamp=t1,
        target_type="event",
        target_id="evt-501",
        changes={"status": {"old": "proposed", "new": "rejected"}},
        notes="False positive: animal triggered motion",
    )
    log2 = AuditLog(
        audit_id="audit-102",
        investigation_id="inv-500",
        action="report_finalize",
        actor="badge-701",
        timestamp=t2,
        target_type="report",
        target_id="rep-500",
        changes={"status": {"old": "draft", "new": "finalized"}},
    )

    repo.add_audit_log(log1)
    repo.add_audit_log(log2)

    # Re-open repo from file to test persistence across connections
    repo.close()
    reloaded_repo = SqliteInvestigationRepository(db_path=db_file)

    fetched1 = reloaded_repo.get_audit_log("audit-101")
    assert fetched1.actor == "badge-701"
    assert fetched1.action == "event_review"
    assert fetched1.notes == "False positive: animal triggered motion"

    all_logs = reloaded_repo.list_audit_logs(investigation_id="inv-500")
    assert len(all_logs) == 2
    assert all_logs[0].audit_id == "audit-101"
    assert all_logs[1].audit_id == "audit-102"
    reloaded_repo.close()
