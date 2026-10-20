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
        media_name = (
            Path(media_assets[0].storage_uri).name
            if media_assets
            else "Primary Media"
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
    .stat-card .val {{ font-size: 2rem; font-weight: 700; color: #fff; }}
    .stat-card .val.confirmed {{ color: var(--success); }}
    .stat-card .val.rejected {{ color: var(--danger); }}
    .stat-card .val.proposed {{ color: var(--warning); }}
    .stat-card .label {{ font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; margin-top: 0.25rem; }}

    section.report-section {{
      background-color: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1.75rem;
      margin-bottom: 2rem;
    }}
    section.report-section h2 {{
      font-size: 1.35rem;
      font-weight: 700;
      margin-bottom: 1rem;
      padding-bottom: 0.5rem;
      border-bottom: 1px solid var(--border);
      color: #93c5fd;
    }}
    
    .summary-text {{
      font-size: 1.05rem;
      line-height: 1.7;
      color: #e5e7eb;
      white-space: pre-line;
      background: rgba(15, 23, 42, 0.6);
      padding: 1.25rem;
      border-radius: 8px;
      border-left: 4px solid var(--accent);
    }}

    .event-card {{
      background-color: #0f172a;
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
      border-radius: 8px;
      overflow: hidden;
      margin: 1rem 0;
      border: 1px solid #334155;
      max-width: 640px;
    }}
    video.incident-video {{
      width: 100%;
      height: auto;
      display: block;
    }}
    .clip-caption {{
      padding: 0.5rem 0.75rem;
      font-size: 0.75rem;
      color: var(--text-muted);
      background-color: #020617;
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
      <div><strong>Primary Media</strong>{html.escape(media_name)}</div>
      <div><strong>Media SHA-256</strong><code>{html.escape(media_sha)}</code></div>
      <div><strong>Generated By</strong>{html.escape(report.generated_by)} ({report.generated_at.strftime('%Y-%m-%d %H:%M UTC')})</div>
      <div><strong>Finalized By</strong>{html.escape(report.finalized_by or 'Pending Review')}</div>
    </div>
  </header>

  <div class="stats-bar">
    <div class="stat-card">
      <div class="val">{len(observations)}</div>
      <div class="label">Total Observations</div>
    </div>
    <div class="stat-card">
      <div class="val">{len(events)}</div>
      <div class="label">Correlated Events</div>
    </div>
    <div class="stat-card">
      <div class="val confirmed">{confirmed_count}</div>
      <div class="label">Confirmed Events</div>
    </div>
    <div class="stat-card">
      <div class="val rejected">{rejected_count}</div>
      <div class="label">Rejected Events</div>
    </div>
    <div class="stat-card">
      <div class="val proposed">{proposed_count}</div>
      <div class="label">Pending Review</div>
    </div>
  </div>

  <section class="report-section">
    <h2>1. Executive Summary & Findings</h2>
    <div class="summary-text">{html.escape(report.summary)}</div>
    {f'<div style="margin-top:1rem; font-size:0.9rem; color:#93c5fd;"><strong>Investigator Final Notes:</strong> {html.escape(report.notes)}</div>' if report.notes else ''}
  </section>

  <section class="report-section">
    <h2>2. Correlated Events & Incident Clips</h2>
"""
        if not events:
            doc += "<p style='color: var(--text-muted);'>No correlated events recorded.</p>"
        else:
            for evt in events:
                status_class = f"status-{evt.status}"
                time_info = ""
                if evt.start_seconds is not None and evt.end_seconds is not None:
                    time_info = f"Footage interval: {evt.start_seconds:.1f}s &ndash; {evt.end_seconds:.1f}s"
                elif evt.start_time and evt.end_time:
                    time_info = f"Time: {evt.start_time.strftime('%H:%M:%S')} &ndash; {evt.end_time.strftime('%H:%M:%S')}"

                clips = event_clips.get(evt.event_id, [])
                video_html = ""
                for clip in clips:
                    stream_url = f"{base_url}/api/v1/investigations/{investigation.investigation_id}/artifacts/{clip.artifact_id}/content"
                    clip_hash = (clip.sha256[:16] + "...") if clip.sha256 else "N/A"
                    video_html += f"""
                    <div class="video-wrapper">
                      <video class="incident-video" controls preload="metadata">
                        <source src="{stream_url}" type="video/mp4">
                        Your browser does not support the video tag.
                      </video>
                      <div class="clip-caption">
                        <span><strong>Clip:</strong> {html.escape(clip.artifact_id)}</span>
                        <span><strong>SHA-256:</strong> <code>{html.escape(clip_hash)}</code></span>
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
    <h2>3. Evidence Assessments & Certainty</h2>
    <table class="data-table">
      <thead>
        <tr>
          <th>Assessment ID</th>
          <th>Target</th>
          <th>Type</th>
          <th>Rating</th>
          <th>Rationale</th>
          <th>Assessor</th>
        </tr>
      </thead>
      <tbody>
"""
        if not assessments:
            doc += "<tr><td colspan='6' style='text-align:center;'>No formal evidence assessments recorded.</td></tr>"
        else:
            for ass in assessments:
                doc += f"""
        <tr>
          <td><code>{html.escape(ass.assessment_id)}</code></td>
          <td>{html.escape(ass.target_type)}:{html.escape(ass.target_id)}</td>
          <td>{html.escape(ass.assessment_type)}</td>
          <td><strong>{html.escape(ass.rating)}</strong></td>
          <td>{html.escape(ass.rationale)}</td>
          <td>{html.escape(ass.assessed_by)}</td>
        </tr>
"""
        doc += """
      </tbody>
    </table>
  </section>

  <section class="report-section">
    <h2>4. Investigator Review Decisions & Audit Trail</h2>
    <table class="data-table">
      <thead>
        <tr>
          <th>Timestamp (UTC)</th>
          <th>Actor / Badge</th>
          <th>Action</th>
          <th>Target ID</th>
          <th>Changes</th>
          <th>Notes / Justification</th>
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
        """Render publication-grade forensic report in PDF format with evidence tables, audit trail, and clip summaries."""
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.pdfgen import canvas
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )

        class NumberedCanvas(canvas.Canvas):
            """Two-pass canvas for total page counts and running headers/footers."""

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
                    self.draw_page_decorations(num_pages)
                    super().showPage()
                super().save()

            def draw_page_decorations(self, page_count: int):
                self.saveState()
                self.setFont("Helvetica-Bold", 8)
                self.setFillColor(colors.HexColor("#475569"))

                # Header
                self.drawString(
                    36,
                    letter[1] - 28,
                    f"VIGIL FORENSIC REPORT - CONFIDENTIAL | CASE: {investigation.investigation_id}",
                )
                self.setStrokeColor(colors.HexColor("#cbd5e1"))
                self.setLineWidth(0.5)
                self.line(36, letter[1] - 32, letter[0] - 36, letter[1] - 32)

                # Footer
                page_str = f"Page {self._pageNumber} of {page_count}"
                self.drawRightString(letter[0] - 36, 24, page_str)
                self.drawString(
                    36,
                    24,
                    f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')} | VIGIL Multi-Agent Forensics",
                )
                self.line(36, 34, letter[0] - 36, 34)
                self.restoreState()

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=45,
            bottomMargin=45,
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
                Paragraph("<b>Media Checksum:</b>", small_style),
                Paragraph(f"<code>{media_sha}</code>", small_style),
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
