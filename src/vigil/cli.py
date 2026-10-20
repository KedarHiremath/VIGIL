"""VIGIL Command-Line Interface supporting server management, human review, audit logs, and report export."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vigil.config import config
from vigil.services.investigation_service import InvestigationService
from vigil.storage.sqlite_repository import SqliteInvestigationRepository


def create_cli_service() -> InvestigationService:
    """Create InvestigationService backed by the persistent SQLite database."""
    db_path = Path(config.storage_root) / "vigil.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    repo = SqliteInvestigationRepository(db_path=db_path)
    return InvestigationService(
        repository=repo,
        storage_dir=config.storage_root,
    )


def handle_serve(args: argparse.Namespace) -> None:
    """Start FastAPI server."""
    import uvicorn

    host = args.host
    port = args.port
    print(f"Starting VIGIL API server on {host}:{port}...")
    uvicorn.run("vigil.api.app:app", host=host, port=port, reload=False)


def handle_review_event(args: argparse.Namespace) -> None:
    """Review an event (confirm, reject, or under_review) via CLI."""
    service = create_cli_service()
    try:
        event, audit_log = service.review_event(
            investigation_id=args.investigation_id,
            event_id=args.event_id,
            status=args.status,
            reviewer=args.reviewer,
            notes=args.notes,
            description=args.description,
        )
        print(f"\n[SUCCESS] Event '{event.event_id}' review updated to '{event.status.upper()}'.")
        print(f"  Reviewer : {event.reviewer}")
        print(f"  Notes    : {event.review_notes or '-'}")
        print(f"  Audit ID : {audit_log.audit_id}")
    finally:
        service.shutdown(wait=False)


def handle_list_events(args: argparse.Namespace) -> None:
    """List events for an investigation with their review status."""
    service = create_cli_service()
    try:
        events = service.get_events(args.investigation_id)
        if args.status:
            events = [e for e in events if e.status.lower() == args.status.lower()]

        print(f"\nEvents for Investigation '{args.investigation_id}' ({len(events)} total):")
        print("-" * 80)
        print(f"{'Event ID':<16} {'Category':<20} {'Status':<14} {'Interval':<16} {'Reviewer'}")
        print("-" * 80)
        for e in events:
            time_str = "-"
            if e.start_seconds is not None and e.end_seconds is not None:
                time_str = f"{e.start_seconds:.1f}s - {e.end_seconds:.1f}s"
            elif e.start_time and e.end_time:
                time_str = f"{e.start_time.strftime('%H:%M:%S')} - {e.end_time.strftime('%H:%M:%S')}"

            reviewer = e.reviewer or "-"
            print(f"{e.event_id:<16} {e.event_type[:19]:<20} {e.status.upper():<14} {time_str:<16} {reviewer}")
        print("-" * 80)
    finally:
        service.shutdown(wait=False)


def handle_audit(args: argparse.Namespace) -> None:
    """Print the chronological audit trail for an investigation."""
    service = create_cli_service()
    try:
        logs = service.get_audit_logs(
            investigation_id=args.investigation_id,
            target_id=args.target_id,
            actor=args.actor,
        )
        print(f"\nAudit Log for Investigation '{args.investigation_id}' ({len(logs)} entries):")
        print("-" * 85)
        print(f"{'Timestamp (UTC)':<20} {'Actor':<16} {'Action':<16} {'Target':<14} {'Changes / Notes'}")
        print("-" * 85)
        for l in logs:
            ts_str = l.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            notes = l.notes or ""
            if l.changes:
                notes = f"{l.changes} {notes}"
            print(f"{ts_str:<20} {l.actor[:15]:<16} {l.action[:15]:<16} {l.target_id[:13]:<14} {notes[:40]}")
        print("-" * 85)
    finally:
        service.shutdown(wait=False)


def handle_finalize(args: argparse.Namespace) -> None:
    """Finalize forensic report with incident clips."""
    service = create_cli_service()
    try:
        report, audit_log = service.finalize_report(
            investigation_id=args.investigation_id,
            finalized_by=args.finalized_by,
            title=args.title,
            summary=args.summary,
            notes=args.notes,
            auto_slice_clips=not args.no_clips,
        )
        print(f"\n[SUCCESS] Report finalized successfully for investigation '{args.investigation_id}'.")
        print(f"  Report ID   : {report.report_id}")
        print(f"  Version     : v{report.version}")
        print(f"  Finalized By: {report.finalized_by}")
        print(f"  Clips Linked: {len(report.clip_artifact_ids)}")
        print(f"  Audit ID    : {audit_log.audit_id}")
    finally:
        service.shutdown(wait=False)


def handle_export(args: argparse.Namespace) -> None:
    """Export report to PDF, HTML, or Markdown."""
    service = create_cli_service()
    try:
        fmt = args.format.lower()
        out_path: Path
        if args.output:
            out_path = Path(args.output).resolve()
        else:
            ext = "pdf" if fmt == "pdf" else ("html" if fmt == "html" else "md")
            out_path = Path(f"report_{args.investigation_id}.{ext}").resolve()

        if fmt == "html":
            content_str = service.export_report_html(
                investigation_id=args.investigation_id,
                report_id=args.report_id,
            )
            out_path.write_text(content_str, encoding="utf-8")
            print(f"\n[SUCCESS] Exported interactive HTML report to: {out_path}")

        elif fmt == "pdf":
            content_bytes = service.export_report_pdf(
                investigation_id=args.investigation_id,
                report_id=args.report_id,
            )
            out_path.write_bytes(content_bytes)
            print(f"\n[SUCCESS] Exported publication PDF report to: {out_path} ({len(content_bytes)} bytes)")

        elif fmt in {"markdown", "md", "text"}:
            report = service.get_report(args.investigation_id)
            if not report:
                print(f"[ERROR] No report found for '{args.investigation_id}'.")
                return
            md_text = (
                f"# {report.title}\n\n"
                f"**Investigation ID**: {report.investigation_id}\n"
                f"**Report ID**: {report.report_id} (v{report.version} - {report.status})\n"
                f"**Generated By**: {report.generated_by}\n\n"
                f"## Executive Summary\n\n{report.summary}\n"
            )
            out_path.write_text(md_text, encoding="utf-8")
            print(f"\n[SUCCESS] Exported Markdown report to: {out_path}")
        else:
            print(f"[ERROR] Unsupported export format '{fmt}'. Choose from: html, pdf, markdown.")
    finally:
        service.shutdown(wait=False)


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser for VIGIL CLI."""
    parser = argparse.ArgumentParser(
        prog="vigil",
        description="VIGIL: Autonomous Video Forensics System CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available subcommands")

    # serve
    serve_parser = subparsers.add_parser("serve", help="Start FastAPI REST and WebSocket server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Binding host (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    serve_parser.set_defaults(func=handle_serve)

    # review
    review_parser = subparsers.add_parser("review", help="Human review workflow commands")
    review_sub = review_parser.add_subparsers(dest="review_command")

    # review event
    rev_event = review_sub.add_parser("event", help="Review an individual proposed event")
    rev_event.add_argument("investigation_id", help="Investigation ID")
    rev_event.add_argument("event_id", help="Event ID")
    rev_event.add_argument(
        "--status",
        required=True,
        choices=["confirmed", "rejected", "under_review", "proposed"],
        help="Review decision status",
    )
    rev_event.add_argument("--reviewer", required=True, help="Investigator badge or username")
    rev_event.add_argument("--notes", help="Forensic review justification or notes")
    rev_event.add_argument("--description", help="Updated event description")
    rev_event.set_defaults(func=handle_review_event)

    # review list-events
    rev_list = review_sub.add_parser("list-events", help="List events and review statuses")
    rev_list.add_argument("investigation_id", help="Investigation ID")
    rev_list.add_argument("--status", help="Filter by review status")
    rev_list.set_defaults(func=handle_list_events)

    # audit
    audit_parser = subparsers.add_parser("audit", help="Inspect investigation audit trail")
    audit_parser.add_argument("investigation_id", help="Investigation ID")
    audit_parser.add_argument("--target-id", help="Filter by targeted record ID")
    audit_parser.add_argument("--actor", help="Filter by investigator/actor")
    audit_parser.set_defaults(func=handle_audit)

    # finalize-report
    finalize_parser = subparsers.add_parser("finalize-report", help="Finalize report and link incident clips")
    finalize_parser.add_argument("investigation_id", help="Investigation ID")
    finalize_parser.add_argument("--finalized-by", required=True, help="Investigator badge or username")
    finalize_parser.add_argument("--title", help="Custom finalized report title")
    finalize_parser.add_argument("--summary", help="Custom finalized executive summary")
    finalize_parser.add_argument("--notes", help="Closing remarks or reviewer notes")
    finalize_parser.add_argument("--no-clips", action="store_true", help="Skip automatic incident clip slicing")
    finalize_parser.set_defaults(func=handle_finalize)

    # export
    export_parser = subparsers.add_parser("export", help="Export report to PDF, HTML, or Markdown")
    export_parser.add_argument("investigation_id", help="Investigation ID")
    export_parser.add_argument("--format", default="html", choices=["html", "pdf", "markdown", "md"], help="Export format")
    export_parser.add_argument("--output", "-o", help="Target output file path")
    export_parser.add_argument("--report-id", help="Specific report ID to export")
    export_parser.set_defaults(func=handle_export)

    return parser


def main() -> None:
    """Main CLI entrypoint."""
    parser = build_parser()
    if len(sys.argv) <= 1:
        print("=================================================================")
        print("  VIGIL: Autonomous Video-Forensics Agentic System")
        print("=================================================================")
        print(f"Active LLM Provider: {config.llm_provider}")
        print(f"Storage Directory  : {config.storage_root}")
        print("Status             : Engine Ready")
        print("Run tests with     : pytest")
        print("Start API with     : vigil serve (or uvicorn vigil.api.app:app)")
        print("Review events with : vigil review event <inv_id> <event_id> --status confirmed --reviewer <name>")
        print("Export reports with: vigil export <inv_id> --format pdf (or --format html)")
        print("=================================================================")
        parser.print_help()
        return

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
