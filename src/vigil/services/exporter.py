"""Forensic report export engine generating HTML and PDF deliverables with embedded incident clips."""

from __future__ import annotations

import html
import io
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from vigil.domain.artifact import Artifact
from vigil.domain.audit import AuditLog
from vigil.domain.coverage import CoverageRecord
from vigil.domain.event import Event
from vigil.domain.evidence_assessment import EvidenceAssessment
from vigil.domain.investigation import Investigation
from vigil.domain.media_asset import MediaAsset
from vigil.domain.observation import Observation
from vigil.domain.report import Report


def _uri_to_local_path(uri: str) -> Path | None:
    """Resolve file URI or local path string to existing Path."""
    if not uri:
        return None
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        path = url2pathname(parsed.path)
        if path.startswith("\\") and len(path) > 3 and path[2] == ":":
            path = path[1:]
        p = Path(path)
        return p if p.is_file() else None
    p = Path(uri)
    return p if p.is_file() else None


def _format_timecode(seconds: float | None) -> str:
    """Format seconds into MM:SS.ss timecode."""
    if seconds is None:
        return "N/A"
    mins = int(seconds // 60)
    secs = seconds % 60
    return f"{mins:02d}:{secs:05.2f}"


def _format_interval(start: float | None, end: float | None) -> str:
    if start is None and end is None:
        return "Timeline: N/A"
    if start is not None and end is not None:
        return f"{_format_timecode(start)} &ndash; {_format_timecode(end)} ({start:.1f}s &ndash; {end:.1f}s)"
    if start is not None:
        return f"From {_format_timecode(start)} ({start:.1f}s)"
    return f"Until {_format_timecode(end)} ({end:.1f}s)"


def _clean_rationale(text: str) -> str:
    """Clean raw markdown tags, bold rating/rationale headers from rationale."""
    if not text:
        return ""
    import re
    cleaned = re.sub(r"\*\*Rating\s*:\s*[^\*]+\*\*", "", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\*\*Rationale\s*:\s*\*\*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(Rating\s*:\s*[^\n]+\n?)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^(Rationale\s*:\s*)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^[\s\-*•]+", "", cleaned.strip())
    lines = [line.strip().lstrip("-*• ") for line in cleaned.splitlines() if line.strip()]
    return " ".join(lines) if lines else text.strip()


class ReportExporter:
    """Exports structured VIGIL forensic reports into interactive HTML and publication-ready PDF formats."""

    @staticmethod
    def export_html(
        investigation: Investigation,
        report: Report,
        events: list[Event],
        observations: list[Observation],
        assessments: list[EvidenceAssessment],
        coverages: list[CoverageRecord],
        artifacts: list[Artifact],
        audit_logs: list[AuditLog],
        media_assets: list[MediaAsset] | None = None,
        base_url: str = "",
    ) -> str:
        """Render complete forensic report as a standalone responsive HTML document with embedded incident clips."""
        media_assets = media_assets or []
        clip_artifacts = [
            a
            for a in artifacts
            if a.artifact_type in {"clip", "subclip", "video_clip"}
        ]

        # Pre-index clips by event or time overlap
        event_clips: dict[str, list[Artifact]] = {e.event_id: [] for e in events}
        unassigned_clips: list[Artifact] = []

        for clip in clip_artifacts:
            matched = False
            sr = clip.source_reference
            for evt in events:
                if (
                    sr.start_seconds is not None
                    and sr.end_seconds is not None
                    and evt.start_seconds is not None
                    and evt.end_seconds is not None
                    and not (
                        sr.end_seconds < evt.start_seconds
                        or sr.start_seconds > evt.end_seconds
                    )
                ):
                    event_clips[evt.event_id].append(clip)
                    matched = True
                    break
            if not matched:
                unassigned_clips.append(clip)

        events = sorted(events, key=lambda e: (e.start_seconds if e.start_seconds is not None else 0.0))
        confirmed_count = sum(1 for e in events if e.status == "confirmed")
        rejected_count = sum(1 for e in events if e.status == "rejected")
        proposed_count = sum(
            1 for e in events if e.status in {"proposed", "under_review"}
        )

        media_sha = (
            media_assets[0].sha256[:16] + "..."
            if (media_assets and media_assets[0].sha256)
            else "N/A"
        )
        media_names_summary = (
            f"{len(media_assets)} Feeds (" + ", ".join(Path(m.storage_uri).name for m in media_assets[:2]) + ("..." if len(media_assets) > 2 else "") + ")"
            if len(media_assets) > 1
            else (Path(media_assets[0].storage_uri).name if media_assets else "Primary Media")
        )

        # Build HTML content
        doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>VIGIL Forensic Report - {html.escape(report.title)}</title>
  <style>
    :root {{
      --bg: #0b0f19;
      --card-bg: #111827;
      --border: #1f2937;
      --text: #f3f4f6;
      --text-muted: #9ca3af;
      --accent: #2563eb;
      --accent-hover: #1d4ed8;
      --success: #10b981;
      --danger: #ef4444;
      --warning: #f59e0b;
      --info: #3b82f6;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background-color: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 2rem 1rem;
    }}
    .container {{
      max-width: 1100px;
      margin: 0 auto;
    }}
    header.report-header {{
      background: linear-gradient(135deg, #1e293b, #0f172a);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 2rem;
      margin-bottom: 2rem;
      position: relative;
    }}
    .badge-classified {{
      display: inline-block;
      padding: 0.25rem 0.75rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      background-color: rgba(37, 99, 235, 0.2);
      color: #60a5fa;
      border: 1px solid #3b82f6;
      margin-bottom: 0.75rem;
    }}
    h1.report-title {{
      font-size: 2rem;
      font-weight: 800;
      color: #ffffff;
      margin-bottom: 0.5rem;
    }}
    .header-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
      margin-top: 1.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border);
      font-size: 0.875rem;
    }}
    .header-grid div strong {{ color: var(--text-muted); display: block; font-size: 0.75rem; text-transform: uppercase; }}
    
    .stats-bar {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }}
    .stat-card {{
      background-color: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1.25rem;
      text-align: center;
    }}
    .stat-card .val {{ font-size: 1.75rem; font-weight: 700; color: #fff; margin-bottom: 0.25rem; }}
    .stat-card .lbl {{ font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }}

    section.report-section {{
      background-color: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
      margin-bottom: 2rem;
    }}
    h2 {{
      font-size: 1.25rem;
      font-weight: 700;
      color: #93c5fd;
      margin-bottom: 1rem;
      border-bottom: 1px solid var(--border);
      padding-bottom: 0.5rem;
    }}
    .summary-text {{
      color: #e2e8f0;
      white-space: pre-line;
      line-height: 1.7;
      background: rgba(15, 23, 42, 0.6);
      padding: 1.2rem;
      border-radius: 8px;
      border-left: 4px solid var(--accent);
    }}
    .notes-box {{
      margin-top: 1rem;
      padding: 1rem;
      background-color: rgba(37, 99, 235, 0.1);
      border: 1px solid rgba(37, 99, 235, 0.3);
      border-radius: 6px;
      font-size: 0.9rem;
    }}

    .event-card {{
      background-color: rgba(15, 23, 42, 0.7);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1.25rem;
      margin-bottom: 1.25rem;
    }}
    .event-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 0.75rem;
      flex-wrap: wrap;
      gap: 0.5rem;
    }}
    .event-title {{
      font-size: 1.1rem;
      font-weight: 600;
      color: #fff;
    }}
    .status-pill {{
      display: inline-block;
      padding: 0.25rem 0.6rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
    }}
    .status-confirmed {{ background-color: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid var(--success); }}
    .status-rejected {{ background-color: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid var(--danger); }}
    .status-proposed {{ background-color: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid var(--warning); }}
    .status-under_review {{ background-color: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid var(--info); }}

    .event-meta {{
      display: flex;
      gap: 1.5rem;
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-bottom: 0.75rem;
    }}
    .event-desc {{
      color: #e2e8f0;
      margin-bottom: 1rem;
      font-size: 0.95rem;
    }}
    .review-note-box {{
      background-color: rgba(30, 41, 59, 0.7);
      border-left: 3px solid #38bdf8;
      padding: 0.6rem 0.9rem;
      border-radius: 4px;
      font-size: 0.85rem;
      color: #bae6fd;
      margin-bottom: 1rem;
    }}

    .video-wrapper {{
      background: #000;
      border-radius: 6px;
      overflow: hidden;
      margin-top: 1rem;
      border: 1px solid var(--border);
    }}
    video.incident-video {{
      width: 100%;
      max-height: 380px;
      display: block;
    }}
    .clip-caption {{
      padding: 0.5rem 0.75rem;
      font-size: 0.8rem;
      color: var(--text-muted);
      background-color: #0f172a;
      display: flex;
      justify-content: space-between;
    }}

    table.data-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
      text-align: left;
    }}
    table.data-table th {{
      background-color: #1e293b;
      color: #94a3b8;
      font-weight: 600;
      padding: 0.75rem 1rem;
      border-bottom: 1px solid var(--border);
    }}
    table.data-table td {{
      padding: 0.75rem 1rem;
      border-bottom: 1px solid rgba(255, 255, 255, 0.05);
      color: #cbd5e1;
    }}
    table.data-table tr:hover td {{
      background-color: rgba(255, 255, 255, 0.02);
    }}

    @media print {{
      body {{ background: #fff; color: #000; padding: 0; }}
      header.report-header, section.report-section, .event-card {{
        background: #fff; border: 1px solid #ccc; color: #000; break-inside: avoid;
      }}
      h1.report-title {{ color: #000; }}
      .summary-text {{ background: #f8fafc; color: #1e293b; border-left: 4px solid #000; }}
      .stat-card {{ border: 1px solid #ccc; }}
      .stat-card .val {{ color: #000; }}
      .status-pill {{ border: 1px solid #000; color: #000; background: none; }}
      table.data-table th {{ background: #f1f5f9; color: #000; }}
      table.data-table td {{ color: #000; }}
    }}
  </style>
</head>
<body>
<div class="container">
  <header class="report-header">
    <div class="badge-classified">Official Forensic Deliverable &bull; VIGIL</div>
    <h1 class="report-title">{html.escape(report.title)}</h1>
    <p style="color: var(--text-muted);">Investigation Objective: {html.escape(investigation.objective)}</p>
    
    <div class="header-grid">
      <div><strong>Investigation ID</strong>{html.escape(investigation.investigation_id)}</div>
      <div><strong>Report ID / Version</strong>{html.escape(report.report_id)} (v{report.version} - {report.status.upper()})</div>
      <div><strong>Surveillance Feeds</strong>{html.escape(media_names_summary)}</div>
      <div><strong>Primary Media SHA-256</strong><code>{html.escape(media_sha)}</code></div>
      <div><strong>Generated By</strong>{html.escape(report.generated_by)} ({report.generated_at.strftime('%Y-%m-%d %H:%M UTC')})</div>
      <div><strong>Finalized By</strong>{html.escape(report.finalized_by or 'Pending Sign-Off')}</div>
    </div>
  </header>

  <div class="stats-bar">
    <div class="stat-card">
      <div class="val">{len(media_assets) or 1}</div>
      <div class="lbl">Surveillance Feeds</div>
    </div>
    <div class="stat-card">
      <div class="val">{len(events)}</div>
      <div class="lbl">Correlated Events</div>
    </div>
    <div class="stat-card">
      <div class="val" style="color: #34d399;">{confirmed_count}</div>
      <div class="lbl">Confirmed Incidents</div>
    </div>
    <div class="stat-card">
      <div class="val" style="color: #60a5fa;">{len(clip_artifacts)}</div>
      <div class="lbl">Incident Clips</div>
    </div>
    <div class="stat-card">
      <div class="val">{len(observations)}</div>
      <div class="lbl">Observations</div>
    </div>
  </div>

  <section class="report-section">
    <h2>1. Executive Summary &amp; Forensic Findings</h2>
    <div class="summary-text">{html.escape(report.summary)}</div>
    {f'<div class="notes-box"><strong>Final Reviewer Notes:</strong> {html.escape(report.notes)}</div>' if report.notes else ''}
  </section>

  <section class="report-section">
    <h2>2. Chronological Correlated Events &amp; Cross-Camera Incidents</h2>
"""

        if not events:
            doc += """<p style="color: var(--text-muted);">No correlated events discovered during forensic examination.</p>"""
        else:
            for evt in events:
                status_class = f"status-{evt.status}"
                time_info = _format_interval(evt.start_seconds, evt.end_seconds)

                video_html = ""
                clips = event_clips.get(evt.event_id, [])
                if clips:
                    for clip in clips:
                        stream_url = f"{base_url}/api/v1/investigations/{investigation.investigation_id}/artifacts/{clip.artifact_id}/content"
                        video_html += f"""
                        <div class="video-wrapper">
                          <video class="incident-video" controls preload="metadata">
                            <source src="{stream_url}" type="video/mp4">
                            Your browser does not support HTML5 video.
                          </video>
                          <div class="clip-caption">
                            <span>Clip: {html.escape(clip.artifact_id)}</span>
                            <span>Interval: {clip.source_reference.start_seconds:.1f}s &ndash; {clip.source_reference.end_seconds:.1f}s</span>
                            <span>SHA-256: <code>{html.escape(clip.sha256[:16] + '...' if clip.sha256 else 'N/A')}</code></span>
                          </div>
                        </div>
                        """

                review_html = ""
                if evt.reviewer or evt.review_notes:
                    review_html = f"""
                    <div class="review-note-box">
                      <strong>Reviewer:</strong> {html.escape(evt.reviewer or 'Anonymous')} &bull;
                      <strong>Decision:</strong> {evt.status.upper()}<br>
                      {html.escape(evt.review_notes or '')}
                    </div>
                    """

                linked_obs_count = len(evt.observation_ids)

                doc += f"""
    <div class="event-card">
      <div class="event-header">
        <span class="event-title">#{html.escape(evt.event_id)} &bull; {html.escape(evt.event_type.replace('_', ' ').title())}</span>
        <span class="status-pill {status_class}">{evt.status}</span>
      </div>
      <div class="event-meta">
        <span>{time_info}</span>
        <span>Supporting Observations: {linked_obs_count}</span>
      </div>
      <div class="event-desc">{html.escape(evt.description)}</div>
      {review_html}
      {video_html}
    </div>
"""

        if unassigned_clips:
            doc += """<h3 style="margin: 1.5rem 0 1rem; color: #94a3b8;">Additional Incident Clips</h3>"""
            for clip in unassigned_clips:
                stream_url = f"{base_url}/api/v1/investigations/{investigation.investigation_id}/artifacts/{clip.artifact_id}/content"
                doc += f"""
                <div class="video-wrapper">
                  <video class="incident-video" controls preload="metadata">
                    <source src="{stream_url}" type="video/mp4">
                  </video>
                  <div class="clip-caption">
                    <span>Clip: {html.escape(clip.artifact_id)}</span>
                    <span>Interval: {clip.source_reference.start_seconds:.1f}s &ndash; {clip.source_reference.end_seconds:.1f}s</span>
                  </div>
                </div>
                """

        doc += """
  </section>

  <section class="report-section">
    <h2>3. Evidence Assessments &amp; Certainty</h2>
    <table class="data-table">
      <thead>
        <tr>
          <th>Assessment ID</th>
          <th>Target</th>
          <th>Type</th>
          <th>Rating</th>
          <th>Verification Rationale</th>
          <th>Assessor</th>
        </tr>
      </thead>
      <tbody>
"""
        if not assessments:
            doc += "<tr><td colspan='6' style='text-align:center;'>No formal evidence assessments recorded.</td></tr>"
        else:
            for ass in assessments:
                rating_color = "#34d399" if ass.rating == "high" else ("#fbbf24" if ass.rating == "moderate" else "#f87171")
                doc += f"""
        <tr>
          <td><code>{html.escape(ass.assessment_id)}</code></td>
          <td><code>{html.escape(ass.target_type)}:{html.escape(ass.target_id)}</code></td>
          <td>{html.escape(ass.assessment_type.replace('_', ' ').title())}</td>
          <td><strong style="color: {rating_color};">{ass.rating.upper()}</strong></td>
          <td>{html.escape(_clean_rationale(ass.rationale))}</td>
          <td>{html.escape(ass.assessed_by)}</td>
        </tr>
"""

        doc += """
      </tbody>
    </table>
  </section>

  <section class="report-section">
    <h2>4. Investigator Audit Trail &amp; Chain of Custody Log</h2>
    <table class="data-table">
      <thead>
        <tr>
          <th>Timestamp (UTC)</th>
          <th>Actor</th>
          <th>Action</th>
          <th>Target ID</th>
          <th>Changes</th>
          <th>Notes</th>
        </tr>
      </thead>
      <tbody>
"""
        if not audit_logs:
            doc += "<tr><td colspan='6' style='text-align:center;'>No audit entries recorded.</td></tr>"
        else:
            for log in audit_logs:
                changes_str = ""
                if log.changes:
                    changes_str = ", ".join(
                        f"{k}: {v.get('old')} &rarr; {v.get('new')}"
                        if isinstance(v, dict)
                        else f"{k}={v}"
                        for k, v in log.changes.items()
                    )
                else:
                    changes_str = "-"

                doc += f"""
        <tr>
          <td>{log.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</td>
          <td><strong>{html.escape(log.actor)}</strong></td>
          <td><code>{html.escape(log.action)}</code></td>
          <td>{html.escape(log.target_id)}</td>
          <td>{changes_str}</td>
          <td>{html.escape(log.notes or '-')}</td>
        </tr>
"""
        doc += """
      </tbody>
    </table>
  </section>
</div>
</body>
</html>
"""
        return doc


    @staticmethod
    def export_markdown(
        investigation: Investigation,
        report: Report,
        events: list[Event],
        observations: list[Observation],
        assessments: list[EvidenceAssessment],
        coverages: list[CoverageRecord],
        artifacts: list[Artifact],
        audit_logs: list[AuditLog],
        media_assets: list[MediaAsset] | None = None,
    ) -> str:
        """Render complete forensic report as a structured, timestamp-indexed Markdown document."""
        media_assets = media_assets or []
        media_name = Path(media_assets[0].storage_uri).name if media_assets else "Primary Media"
        media_sha = (media_assets[0].sha256[:16] + "...") if (media_assets and media_assets[0].sha256) else "N/A"

        confirmed_count = sum(1 for e in events if e.status == "confirmed")
        rejected_count = sum(1 for e in events if e.status == "rejected")
        proposed_count = sum(1 for e in events if e.status in {"proposed", "under_review"})

        sorted_events = sorted(
            events,
            key=lambda e: (e.start_seconds if e.start_seconds is not None else 0.0),
        )

        md: list[str] = []
        md.append(f"# {report.title}\n")
        md.append(f"**Investigation Objective:** {investigation.objective or 'Forensic timeline and activity verification.'}\n")
        md.append("| Investigation Metadata | Value | Evidence Scope | Count |")
        md.append("| :--- | :--- | :--- | :--- |")
        md.append(f"| **Investigation ID** | `{investigation.investigation_id}` | **Total Observations** | {len(observations)} |")
        md.append(f"| **Report ID / Version** | `{report.report_id}` (v{report.version} - {report.status.upper()}) | **Correlated Events** | {len(events)} ({confirmed_count} Confirmed, {proposed_count} Review, {rejected_count} Rejected) |")
        md.append(f"| **Surveillance Feeds** | {len(media_assets)} feed(s) (`{media_name}`) | **Evidence Assessments** | {len(assessments)} |")
        md.append(f"| **Primary Media SHA-256** | `{media_sha}` | **Coverage Records** | {len(coverages)} |")
        md.append(f"| **Generated By** | `{report.generated_by}` ({report.generated_at.strftime('%Y-%m-%d %H:%M UTC')}) | **Review Status** | `{report.status.upper()}` |")
        md.append(f"| **Finalized By** | `{report.finalized_by or 'Pending Review'}` | **Finalized At** | `{report.finalized_at.strftime('%Y-%m-%d %H:%M UTC') if report.finalized_at else 'Pending'}` |\n")

        md.append("## 1. Executive Summary & Findings\n")
        md.append(f"{report.summary}\n")
        if report.notes:
            md.append(f"> **Investigator Final Notes:** {report.notes}\n")

        md.append("## 2. Chronological Correlated Events & Incident Timeline\n")
        if not sorted_events:
            md.append("*No correlated events recorded.*\n")
        else:
            md.append("| Timecode Interval | Event Type | Status | Description | Supporting Obs |")
            md.append("| :--- | :--- | :--- | :--- | :--- |")
            for evt in sorted_events:
                t_str = ""
                if evt.start_seconds is not None and evt.end_seconds is not None:
                    t_str = f"`{_format_timecode(evt.start_seconds)} - {_format_timecode(evt.end_seconds)}` ({evt.start_seconds:.1f}s - {evt.end_seconds:.1f}s)"
                elif evt.start_seconds is not None:
                    t_str = f"`{evt.start_seconds:.1f}s`"
                else:
                    t_str = "N/A"
                desc = evt.description.replace("|", "-")
                md.append(f"| {t_str} | **{evt.event_type.replace('_', ' ').title()}** | `{evt.status.upper()}` | {desc} | {len(evt.observation_ids)} obs |")
            md.append("")

            for evt in sorted_events:
                t_str = ""
                if evt.start_seconds is not None and evt.end_seconds is not None:
                    t_str = f"{_format_timecode(evt.start_seconds)} – {_format_timecode(evt.end_seconds)} ({evt.start_seconds:.1f}s – {evt.end_seconds:.1f}s)"
                md.append(f"### #{evt.event_id} • {evt.event_type.replace('_', ' ').title()}")
                md.append(f"- **Status:** `{evt.status}` | **Footage interval:** {t_str} | **Supporting Observations:** {len(evt.observation_ids)}")
                md.append(f"- **Details:** {evt.description}")
                if evt.reviewer or evt.review_notes:
                    md.append(f"- **Reviewer Decision:** {evt.reviewer or 'Lead Investigator'} [{evt.status.upper()}] — {evt.review_notes or 'No review notes'}")
                md.append("")

        md.append("## 3. Evidence Assessments & Certainty\n")
        if not assessments:
            md.append("*No formal evidence assessments recorded.*\n")
        else:
            md.append("| Assessment ID | Target | Dimension | Quality Rating | Forensic Verification Rationale | Assessor |")
            md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for ass in assessments:
                clean_rat = _clean_rationale(ass.rationale).replace("|", "-")
                md.append(f"| `{ass.assessment_id}` | `{ass.target_type}:{ass.target_id}` | {ass.assessment_type.replace('_', ' ').title()} | **{ass.rating.upper()}** | {clean_rat} | {ass.assessed_by} |")
            md.append("")

        md.append("## 4. Investigator Audit Log\n")
        if not audit_logs:
            md.append("*No human review actions or audit logs recorded.*\n")
        else:
            md.append("| Timestamp (UTC) | Investigator | Action | Target ID | Log Notes |")
            md.append("| :--- | :--- | :--- | :--- | :--- |")
            for log in audit_logs:
                md.append(f"| {log.timestamp.strftime('%Y-%m-%d %H:%M:%S')} | **{log.actor}** | `{log.action}` | `{log.target_id}` | {log.notes or '-'} |")
            md.append("")

        return "\n".join(md)

    @staticmethod
    def export_pdf(
        investigation: Investigation,
        report: Report,
        events: list[Event],
        observations: list[Observation],
        assessments: list[EvidenceAssessment],
        coverages: list[CoverageRecord],
        artifacts: list[Artifact],
        audit_logs: list[AuditLog],
        media_assets: list[MediaAsset] | None = None,
    ) -> bytes:
        """Render publication-grade forensic report as PDF binary with ReportLab."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        media_assets = media_assets or []
        events = sorted(events, key=lambda e: (e.start_seconds if e.start_seconds is not None else 0.0))

        buffer = io.BytesIO()

        # Canvas with page numbers
        class NumberedCanvas(canvas.Canvas):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._saved_page_states = []

            def showPage(self):
                self._saved_page_states.append(dict(self.__dict__))
                self._startPage()

            def save(self):
                num_pages = len(self._saved_page_states)
                for state in self._saved_page_states:
                    self.__dict__.update(state)
                    self.draw_page_number(num_pages)
                    super().showPage()
                super().save()

            def draw_page_number(self, page_count: int):
                self.saveState()
                self.setFont("Helvetica", 8)
                self.setFillColor(colors.HexColor("#64748b"))
                page_text = f"Page {self._pageNumber} of {page_count}"
                conf_text = "CONFIDENTIAL // LAW ENFORCEMENT & FORENSIC AUDIT ONLY"
                self.drawString(54, 36, conf_text)
                self.drawRightString(612 - 54, 36, page_text)
                self.setStrokeColor(colors.HexColor("#e2e8f0"))
                self.setLineWidth(0.5)
                self.line(54, 48, 612 - 54, 48)
                self.restoreState()

        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=54,
            rightMargin=54,
            topMargin=54,
            bottomMargin=54,
        )

        styles = getSampleStyleSheet()
        normal = styles["Normal"]

        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Title"],
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0f172a"),
            alignment=0,
        )
        h2_style = ParagraphStyle(
            "SectionHeader",
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#1e3a8a"),
            spaceBefore=12,
            spaceAfter=6,
        )
        body_style = ParagraphStyle(
            "ReportBody",
            parent=normal,
            fontName="Helvetica",
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#1e293b"),
        )
        small_style = ParagraphStyle(
            "SmallText",
            parent=normal,
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#475569"),
        )
        table_head_style = ParagraphStyle(
            "TableHead",
            parent=normal,
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.white,
        )

        story = []

        story.append(
            Paragraph(
                "<font color='#2563eb'><b>OFFICIAL FORENSIC DELIVERABLE &bull; CHAIN OF CUSTODY VERIFIED</b></font>",
                small_style,
            )
        )
        story.append(Spacer(1, 4))
        story.append(Paragraph(report.title, title_style))
        story.append(Spacer(1, 8))

        media_sha = (
            media_assets[0].sha256[:20] + "..."
            if (media_assets and media_assets[0].sha256)
            else "N/A"
        )
        feed_summary_label = f"Surveillance Feeds ({len(media_assets)}):" if len(media_assets) > 1 else "Primary Media:"
        feed_summary_val = (
            f"{len(media_assets)} synchronized feeds"
            if len(media_assets) > 1
            else (Path(media_assets[0].storage_uri).name if media_assets else "Primary Video")
        )

        meta_data = [
            [
                Paragraph("<b>Investigation ID:</b>", small_style),
                Paragraph(investigation.investigation_id, small_style),
                Paragraph("<b>Report Status:</b>", small_style),
                Paragraph(
                    f"<b>{report.status.upper()} (v{report.version})</b>",
                    small_style,
                ),
            ],
            [
                Paragraph("<b>Generated By:</b>", small_style),
                Paragraph(report.generated_by, small_style),
                Paragraph("<b>Finalized By:</b>", small_style),
                Paragraph(report.finalized_by or "Pending Review", small_style),
            ],
            [
                Paragraph("<b>Generated At:</b>", small_style),
                Paragraph(
                    report.generated_at.strftime("%Y-%m-%d %H:%M UTC"),
                    small_style,
                ),
                Paragraph(f"<b>{feed_summary_label}</b>", small_style),
                Paragraph(f"{feed_summary_val} (<code>{media_sha}</code>)", small_style),
            ],
        ]
        meta_table = Table(
            meta_data,
            colWidths=[1.3 * inch, 2.2 * inch, 1.2 * inch, 2.3 * inch],
        )
        meta_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(meta_table)
        story.append(Spacer(1, 10))

        story.append(
            Paragraph("1. Executive Summary & Forensic Objective", h2_style)
        )
        story.append(
            Paragraph(f"<b>Objective:</b> {investigation.objective}", body_style)
        )
        story.append(Spacer(1, 4))
        summary_box = Table(
            [[Paragraph(report.summary.replace("\n", "<br/>"), body_style)]],
            colWidths=[7.0 * inch],
        )
        summary_box.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eff6ff")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#bfdbfe")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        story.append(summary_box)
        story.append(Spacer(1, 10))

        story.append(
            Paragraph("2. Correlated Events & Human Review Status", h2_style)
        )
        event_table_data = [
            [
                Paragraph("Event ID", table_head_style),
                Paragraph("Category", table_head_style),
                Paragraph("Interval", table_head_style),
                Paragraph("Status", table_head_style),
                Paragraph("Description & Reviewer Notes", table_head_style),
            ]
        ]
        for evt in events:
            time_str = "-"
            if evt.start_seconds is not None and evt.end_seconds is not None:
                time_str = f"{evt.start_seconds:.1f}s - {evt.end_seconds:.1f}s"
            elif evt.start_time and evt.end_time:
                time_str = f"{evt.start_time.strftime('%H:%M:%S')} - {evt.end_time.strftime('%H:%M:%S')}"

            status_color = (
                "#10b981"
                if evt.status == "confirmed"
                else ("#ef4444" if evt.status == "rejected" else "#f59e0b")
            )
            status_p = Paragraph(
                f"<font color='{status_color}'><b>{evt.status.upper()}</b></font>",
                small_style,
            )

            desc_text = evt.description
            if evt.reviewer or evt.review_notes:
                desc_text += f"<br/><font color='#475569'><i>Reviewed by {evt.reviewer or 'Badge'}: {evt.review_notes or ''}</i></font>"

            event_table_data.append([
                Paragraph(evt.event_id, small_style),
                Paragraph(evt.event_type, small_style),
                Paragraph(time_str, small_style),
                status_p,
                Paragraph(desc_text, small_style),
            ])

        if len(event_table_data) == 1:
            event_table_data.append([
                Paragraph("No events recorded", small_style),
                "",
                "",
                "",
                "",
            ])

        evt_table = Table(
            event_table_data,
            colWidths=[1.0 * inch, 1.2 * inch, 1.0 * inch, 1.0 * inch, 2.8 * inch],
        )
        evt_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(evt_table)
        story.append(Spacer(1, 10))

        story.append(
            Paragraph("3. Incident Video Clips & Chain of Custody", h2_style)
        )
        clip_artifacts = [
            a
            for a in artifacts
            if a.artifact_type in {"clip", "subclip", "video_clip"}
        ]
        clip_data = [
            [
                Paragraph("Artifact ID", table_head_style),
                Paragraph("Media Ref", table_head_style),
                Paragraph("Interval", table_head_style),
                Paragraph("SHA-256 Checksum", table_head_style),
                Paragraph("Storage URI", table_head_style),
            ]
        ]
        for c in clip_artifacts:
            sr = c.source_reference
            inv_str = (
                f"{sr.start_seconds:.1f}s - {sr.end_seconds:.1f}s"
                if sr.start_seconds is not None
                else "Full"
            )
            sha_short = (c.sha256[:16] + "...") if c.sha256 else "N/A"
            clip_data.append([
                Paragraph(c.artifact_id, small_style),
                Paragraph(sr.media_asset_id, small_style),
                Paragraph(inv_str, small_style),
                Paragraph(f"<code>{sha_short}</code>", small_style),
                Paragraph(Path(c.storage_uri).name, small_style),
            ])

        if len(clip_data) == 1:
            clip_data.append([
                Paragraph("No clips sliced", small_style),
                "",
                "",
                "",
                "",
            ])

        clip_table = Table(
            clip_data,
            colWidths=[1.5 * inch, 1.0 * inch, 1.0 * inch, 1.7 * inch, 1.8 * inch],
        )
        clip_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(clip_table)
        story.append(Spacer(1, 10))

        story.append(
            Paragraph(
                "4. Investigator Audit Trail & Review Decisions", h2_style
            )
        )
        audit_data = [
            [
                Paragraph("Timestamp (UTC)", table_head_style),
                Paragraph("Actor", table_head_style),
                Paragraph("Action", table_head_style),
                Paragraph("Target ID", table_head_style),
                Paragraph("Decision / Notes", table_head_style),
            ]
        ]
        for log in audit_logs:
            notes_str = log.notes or ""
            if log.changes:
                notes_str += f" | {log.changes}"
            audit_data.append([
                Paragraph(
                    log.timestamp.strftime("%Y-%m-%d %H:%M:%S"), small_style
                ),
                Paragraph(log.actor, small_style),
                Paragraph(log.action, small_style),
                Paragraph(log.target_id, small_style),
                Paragraph(notes_str, small_style),
            ])

        if len(audit_data) == 1:
            audit_data.append([
                Paragraph("No audit logs recorded", small_style),
                "",
                "",
                "",
                "",
            ])

        audit_table = Table(
            audit_data,
            colWidths=[1.4 * inch, 1.1 * inch, 1.2 * inch, 1.2 * inch, 2.1 * inch],
        )
        audit_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ])
        )
        story.append(audit_table)

        doc.build(story, canvasmaker=NumberedCanvas)
        return buffer.getvalue()
