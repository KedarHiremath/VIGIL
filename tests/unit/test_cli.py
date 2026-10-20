"""Unit tests for VIGIL Command-Line Interface."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from vigil.cli import build_parser, main
from vigil.domain.event import Event
from vigil.domain.investigation import Investigation
from vigil.orchestration.investigation_state import (
    InvestigationState,
    InvestigationStatus,
)
from vigil.services.investigation_service import InvestigationService
from vigil.storage.sqlite_repository import SqliteInvestigationRepository


def test_cli_parser_building() -> None:
    parser = build_parser()
    assert parser.prog == "vigil"

    # Test review parser
    args = parser.parse_args([
        "review", "event", "inv-01", "evt-01",
        "--status", "confirmed",
        "--reviewer", "officer-davis",
        "--notes", "Confirmed incident",
    ])
    assert args.command == "review"
    assert args.review_command == "event"
    assert args.investigation_id == "inv-01"
    assert args.status == "confirmed"
    assert args.reviewer == "officer-davis"


def test_cli_review_and_audit_execution(tmp_path: Path, monkeypatch, capsys) -> None:
    db_file = tmp_path / "cli_test.db"
    repo = SqliteInvestigationRepository(db_path=db_file)
    service = InvestigationService(repository=repo, storage_dir=tmp_path / "storage")

    inv = Investigation(
        investigation_id="inv-cli-01",
        title="CLI Investigation",
        objective="Test CLI review workflows",
        scope_description="Testing",
        media_asset_ids=["media-01"],
    )
    repo.add_investigation(inv)
    now = datetime.now(UTC)
    state = InvestigationState(
        investigation_id="inv-cli-01",
        status=InvestigationStatus.COMPLETED,
        completed_at=now,
        event_ids=["evt-cli-01"],
    )
    repo.save_state(state)
    event = Event(
        event_id="evt-cli-01",
        event_type="perimeter_breach",
        description="Gate breach",
        observation_ids=["obs-01"],
        status="proposed",
    )
    repo.add_event(event)

    with patch("vigil.cli.create_cli_service", return_value=service):
        # 1. Review event
        with patch.object(sys, "argv", [
            "vigil", "review", "event", "inv-cli-01", "evt-cli-01",
            "--status", "confirmed",
            "--reviewer", "investigator-brown",
            "--notes", "Confirmed from CCTV footage",
        ]):
            main()
            captured = capsys.readouterr()
            assert "[SUCCESS]" in captured.out
            assert "CONFIRMED" in captured.out

        # 2. List events
        with patch.object(sys, "argv", [
            "vigil", "review", "list-events", "inv-cli-01",
        ]):
            main()
            captured = capsys.readouterr()
            assert "evt-cli-01" in captured.out
            assert "CONFIRMED" in captured.out

        # 3. Audit logs
        with patch.object(sys, "argv", [
            "vigil", "audit", "inv-cli-01",
        ]):
            main()
            captured = capsys.readouterr()
            assert "investigator-br" in captured.out or "investigator-brown" in captured.out
            assert "event_review" in captured.out

        # 4. Finalize report
        with patch.object(sys, "argv", [
            "vigil", "finalize-report", "inv-cli-01",
            "--finalized-by", "chief-inspector",
            "--no-clips",
        ]):
            main()
            captured = capsys.readouterr()
            assert "[SUCCESS]" in captured.out
            assert "chief-inspector" in captured.out

        # 5. Export HTML
        out_html = tmp_path / "report.html"
        with patch.object(sys, "argv", [
            "vigil", "export", "inv-cli-01",
            "--format", "html",
            "--output", str(out_html),
        ]):
            main()
            captured = capsys.readouterr()
            assert "[SUCCESS]" in captured.out
            assert out_html.is_file()
            assert "<!DOCTYPE html>" in out_html.read_text(encoding="utf-8")

        # 6. Export PDF
        out_pdf = tmp_path / "report.pdf"
        with patch.object(sys, "argv", [
            "vigil", "export", "inv-cli-01",
            "--format", "pdf",
            "--output", str(out_pdf),
        ]):
            main()
            captured = capsys.readouterr()
            assert "[SUCCESS]" in captured.out
            assert out_pdf.is_file()
            assert out_pdf.read_bytes().startswith(b"%PDF-")
