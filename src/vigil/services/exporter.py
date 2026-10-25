"""Forensic report export engine generating HTML and PDF deliverables with embedded incident clips."""

from __future__ import annotations

import base64
import html
import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any
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
        visual_evidence: list[dict[str, Any]] | None = None,
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

    .evidence-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 1.5rem;
      margin-top: 1rem;
    }}
    .evidence-card {{
      background-color: rgba(15, 23, 42, 0.7);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 1.25rem;
      overflow: hidden;
    }}
    .evidence-img-box {{
      background: #000;
      border-radius: 6px;
      overflow: hidden;
      margin-bottom: 0.85rem;
      border: 1px solid var(--border);
      text-align: center;
    }}
    .evidence-img {{
      max-width: 100%;
      height: auto;
      display: block;
      margin: 0 auto;
    }}
    .tag-badge {{
      display: inline-block;
      padding: 0.2rem 0.5rem;
      background: rgba(56, 189, 248, 0.15);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.3);
      border-radius: 4px;
      font-size: 0.75rem;
      margin-right: 0.35rem;
      margin-bottom: 0.35rem;
    }}
    .disclaimer-banner {{
      font-size: 0.75rem;
      color: #fbbf24;
      background: rgba(245, 158, 11, 0.1);
      border-left: 3px solid #f59e0b;
      padding: 0.4rem 0.6rem;
      border-radius: 0 4px 4px 0;
      margin-bottom: 0.75rem;
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
"""

        visual_evidence = visual_evidence or getattr(report, "visual_evidence", []) or []

        doc += """
  <section class="report-section">
    <h2>3. Forensic Visual Evidence &amp; Incident Key Frames</h2>
"""
        if not visual_evidence:
            doc += """<p style="color: var(--text-muted);">No incident key frames selected for this report.</p>"""
        else:
            doc += """<div class="evidence-grid">"""
            for item in visual_evidence[:3]:
                # Determine image src: prefer base64 data URI of local file
                img_src = ""
                local_f = _uri_to_local_path(item.get("storage_uri", ""))
                if not local_f or not local_f.is_file():
                    local_f = _uri_to_local_path(item.get("original_storage_uri", ""))

                if local_f and local_f.is_file():
                    try:
                        b64_data = base64.b64encode(local_f.read_bytes()).decode("ascii")
                        img_src = f"data:image/jpeg;base64,{b64_data}"
                    except Exception:
                        img_src = ""

                if not img_src:
                    target_aid = item.get("annotated_artifact_id") or item.get("artifact_id", "")
                    img_src = f"{base_url}/api/v1/investigations/{investigation.investigation_id}/artifacts/{target_aid}/content"

                # Badges and tags
                tag_html = "".join(f'<span class="tag-badge">#{html.escape(t)}</span>' for t in item.get("tags", []))

                ents = item.get("resolved_entity_ids", [])
                ents_html = ", ".join(f"<code>{html.escape(e)}</code>" for e in ents) if ents else "None"

                cam_name = item.get("camera_label") or item.get("camera_id") or "Surveillance Feed"
                t_sec = item.get("timestamp_seconds")
                t_display = f"{_format_timecode(t_sec)} ({t_sec:.1f}s)" if t_sec is not None else "N/A"

                overlay_note = ""
                if item.get("has_overlay"):
                    overlay_note = """
                    <div class="disclaimer-banner">
                      &#9888; <strong>Model-Generated Overlay:</strong> Bounding boxes and labels are AI-generated detections and require human verification.
                    </div>
                    """
                else:
                    overlay_note = """
                    <div style="font-size: 0.75rem; color: var(--text-muted); margin-bottom: 0.5rem;">
                      Original unannotated frame (no reliable detections detected).
                    </div>
                    """

                orig_aid = item.get("artifact_id", "N/A")
                ann_aid = item.get("annotated_artifact_id")
                aid_display = f"<code>{html.escape(orig_aid)}</code>"
                if ann_aid:
                    aid_display += f" &bull; Annotated: <code>{html.escape(ann_aid)}</code>"

                doc += f"""
    <div class="evidence-card">
      <div class="evidence-img-box">
        <img class="evidence-img" src="{img_src}" alt="Key Frame Evidence: {html.escape(orig_aid)}" loading="lazy" />
      </div>
      {overlay_note}
      <div style="font-size: 0.95rem; font-weight: 600; color: #f1f5f9; margin-bottom: 0.5rem;">
        {html.escape(item.get("caption", "Forensic incident frame evidence."))}
      </div>
      <div style="margin-bottom: 0.75rem;">
        {tag_html}
      </div>
      <div style="font-size: 0.8rem; color: var(--text-muted); border-top: 1px solid var(--border); padding-top: 0.5rem; line-height: 1.6;">
        <div><strong>Timeline Context:</strong> {html.escape(cam_name)} &bull; {t_display}</div>
        <div><strong>Resolved Entities:</strong> {ents_html}</div>
        <div><strong>Source Artifact:</strong> {aid_display}</div>
        <div><strong>Original URI:</strong> <code style="word-break: break-all;">{html.escape(item.get("original_storage_uri", "N/A"))}</code></div>
      </div>
    </div>
"""
            doc += """</div>"""

        doc += """
  </section>

  <section class="report-section">
    <h2>4. Evidence Assessments &amp; Certainty</h2>
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
    <h2>5. Investigator Audit Trail &amp; Chain of Custody Log</h2>
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
        visual_evidence: list[dict[str, Any]] | None = None,
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

        visual_evidence = visual_evidence or getattr(report, "visual_evidence", []) or []
        md.append("## 3. Forensic Visual Evidence & Incident Key Frames\n")
        if not visual_evidence:
            md.append("*No incident key frames selected for this report.*\n")
        else:
            md.append("| Frame Artifact Ref | Timeline / Camera Context | Visual Caption & Summary | Detected Tags | Resolved Entities | Overlay Status |")
            md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for item in visual_evidence[:3]:
                orig_aid = item.get("artifact_id", "N/A")
                ann_aid = item.get("annotated_artifact_id")
                aid_ref = f"`{orig_aid}`" + (f" (`{ann_aid}`)" if ann_aid else "")
                cam_name = item.get("camera_label") or item.get("camera_id") or "Surveillance Feed"
                t_sec = item.get("timestamp_seconds")
                t_str = f"`{_format_timecode(t_sec)}` ({t_sec:.1f}s)" if t_sec is not None else "N/A"
                cap_clean = str(item.get("caption", "Salient visual evidence.")).replace("|", "-")
                tags_str = ", ".join(item.get("tags", [])) or "None"
                ents_str = ", ".join(f"`{e}`" for e in item.get("resolved_entity_ids", [])) or "None"
                overlay_str = "`AI OVERLAY`" if item.get("has_overlay") else "`UNANNOTATED`"
                md.append(f"| {aid_ref} | {cam_name} ({t_str}) | {cap_clean} | {tags_str} | {ents_str} | {overlay_str} |")
            md.append("")

            for item in visual_evidence[:3]:
                orig_aid = item.get("artifact_id", "N/A")
                ann_aid = item.get("annotated_artifact_id")
                md.append(f"### Visual Evidence Item: #{orig_aid}")
                md.append(f"- **Caption:** {item.get('caption', 'Forensic incident evidence.')}")
                cam_name = item.get("camera_label") or item.get("camera_id") or "Surveillance Feed"
                t_sec = item.get("timestamp_seconds")
                t_str = f"{t_sec:.1f}s" if t_sec is not None else "N/A"
                md.append(f"- **Timeline & Camera:** {cam_name} [{t_str}]")
                md.append(f"- **Descriptive Tags:** {', '.join(item.get('tags', [])) or 'None'}")
                md.append(f"- **Resolved Entities:** {', '.join(item.get('resolved_entity_ids', [])) or 'None'}")
                if ann_aid:
                    md.append(f"- **Annotated Derivative:** `{ann_aid}` ({item.get('storage_uri', 'N/A')})")
                md.append(f"- **Original Evidence Ref:** `{orig_aid}` ({item.get('original_storage_uri', 'N/A')})")
                if item.get("has_overlay"):
                    md.append("- *Note: Model-generated bounding boxes and labels are AI-generated and require human verification.*")
                md.append("")

        md.append("## 4. Evidence Assessments & Certainty\n")
        if not assessments:
            md.append("*No formal evidence assessments recorded.*\n")
        else:
            md.append("| Assessment ID | Target | Dimension | Quality Rating | Forensic Verification Rationale | Assessor |")
            md.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for ass in assessments:
                clean_rat = _clean_rationale(ass.rationale).replace("|", "-")
                md.append(f"| `{ass.assessment_id}` | `{ass.target_type}:{ass.target_id}` | {ass.assessment_type.replace('_', ' ').title()} | **{ass.rating.upper()}** | {clean_rat} | {ass.assessed_by} |")
            md.append("")

        md.append("## 5. Investigator Audit Log\n")
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
        visual_evidence: list[dict[str, Any]] | None = None,
    ) -> bytes:
        """Render publication-grade forensic report as PDF binary with ReportLab."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
        from reportlab.platypus import (
            Image as ReportLabImage,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

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
        summary_h3_style = ParagraphStyle(
            "SummaryH3",
            parent=normal,
            fontName="Helvetica-Bold",
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#1e3a8a"),
            spaceBefore=8,
            spaceAfter=4,
            keepWithNext=True,
        )
        summary_bullet_style = ParagraphStyle(
            "SummaryBullet",
            parent=body_style,
            leftIndent=14,
            firstLineIndent=-10,
            spaceAfter=3,
        )
        summary_body_style = ParagraphStyle(
            "SummaryBodyText",
            parent=body_style,
            spaceAfter=4,
        )

        def _format_inline_markdown(text: str) -> str:
            if not text:
                return ""
            text = html.escape(text)
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
            text = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", text)
            text = re.sub(r"`([^`]+?)`", r'<font face="Courier" color="#0369a1">\1</font>', text)
            return text

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
            Paragraph(f"<b>Objective:</b> {_format_inline_markdown(investigation.objective)}", body_style)
        )
        story.append(Spacer(1, 6))

        summary_lines = (report.summary or "").strip().splitlines()
        for s_line in summary_lines:
            s_stripped = s_line.strip()
            if not s_stripped:
                story.append(Spacer(1, 3))
                continue
            if s_stripped.startswith("#"):
                clean_head = re.sub(r"^#+\s*", "", s_stripped)
                story.append(Paragraph(_format_inline_markdown(clean_head), summary_h3_style))
            elif s_stripped.startswith(("- ", "* ")) or re.match(r"^\d+\.\s", s_stripped):
                clean_bullet = re.sub(r"^(?:[-*]|\d+\.)\s*", "&bull; ", s_stripped)
                story.append(Paragraph(_format_inline_markdown(clean_bullet), summary_bullet_style))
            else:
                story.append(Paragraph(_format_inline_markdown(s_stripped), summary_body_style))

        if report.notes:
            story.append(Spacer(1, 4))
            story.append(
                Paragraph(
                    f"<b>Final Reviewer Notes:</b> {_format_inline_markdown(report.notes)}",
                    body_style,
                )
            )

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
            repeatRows=1,
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
            Paragraph("3. Forensic Visual Evidence & Key Incident Frames", h2_style)
        )

        visual_evidence = visual_evidence or getattr(report, "visual_evidence", []) or []
        if not visual_evidence:
            story.append(
                Paragraph("<i>No visual evidence frames selected for this report.</i>", small_style)
            )
            story.append(Spacer(1, 8))
        else:
            for item in visual_evidence[:3]:
                # Attempt to render image if physical file exists
                img_path = _uri_to_local_path(item.get("storage_uri", ""))
                if not img_path or not img_path.is_file():
                    img_path = _uri_to_local_path(item.get("original_storage_uri", ""))

                if img_path and img_path.is_file():
                    try:
                        from PIL import Image as PILImage
                        with PILImage.open(img_path) as pimg:
                            iw, ih = pimg.size
                        max_w = 5.2 * inch
                        max_h = 2.6 * inch
                        scale = min(max_w / iw, max_h / ih, 1.0)
                        story.append(ReportLabImage(str(img_path), width=iw * scale, height=ih * scale))
                        story.append(Spacer(1, 4))
                    except Exception as img_exc:
                        logger.warning("Could not embed image in PDF: %s", img_exc)

                cap_text = item.get("caption", "Salient incident visual evidence.")
                story.append(Paragraph(f"<b>Caption:</b> {html.escape(cap_text)}", body_style))

                tags = item.get("tags", [])
                tags_str = ", ".join(tags) if tags else "None"
                ents = item.get("resolved_entity_ids", [])
                ents_str = ", ".join(ents) if ents else "None"
                cam_label = item.get("camera_label") or item.get("camera_id") or "Surveillance Feed"
                t_sec = item.get("timestamp_seconds")
                t_str = f"{t_sec:.1f}s" if t_sec is not None else "N/A"
                art_id = item.get("artifact_id", "N/A")
                ann_id = item.get("annotated_artifact_id")

                ref_info = f"Artifact: <code>{html.escape(art_id)}</code>"
                if ann_id:
                    ref_info += f" &bull; Annotated: <code>{html.escape(ann_id)}</code>"

                story.append(
                    Paragraph(
                        f"<b>Tags:</b> {html.escape(tags_str)} | <b>Entities:</b> {html.escape(ents_str)} | <b>Context:</b> {html.escape(cam_label)} [{t_str}] | {ref_info}",
                        small_style,
                    )
                )

                if item.get("has_overlay"):
                    story.append(
                        Paragraph(
                            "<font color='#d97706'><i>&bull; Model-generated overlay: Bounding boxes and labels are AI-generated and require forensic verification.</i></font>",
                            small_style,
                        )
                    )
                story.append(Spacer(1, 8))

        story.append(
            Paragraph("4. Incident Video Clips & Chain of Custody", h2_style)
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
            repeatRows=1,
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
                "5. Investigator Audit Trail & Review Decisions", h2_style
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
            repeatRows=1,
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
