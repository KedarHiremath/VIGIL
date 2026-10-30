"""Coverage tracker worker recording forensic examination status."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from vigil.domain.coverage import CoverageRecord, CoverageStatus
from vigil.orchestration.task_types import TaskRequest
from vigil.tools.base import BaseToolWorker

logger = logging.getLogger(__name__)


class CoverageTrackerWorker(BaseToolWorker):
    """Tracks examination intervals and creates truthful CoverageRecords with gap detection."""

    def run(self, request: TaskRequest) -> list[str]:
        investigation_id = str(
            request.parameters.get("investigation_id", "inv-default")
        )
        source_ref_ids = list(request.input_refs)

        if not source_ref_ids:
            try:
                inv = self.repository.get_investigation(investigation_id)
                source_ref_ids = list(inv.media_asset_ids)
            except Exception:
                pass

        if not source_ref_ids:
            media_assets = self.repository.list_media_assets()
            if media_assets:
                source_ref_ids = [m.media_asset_id for m in media_assets]
            else:
                source_ref_ids = ["src-media-001"]

        all_artifacts = self.repository.list_artifacts()
        output_coverage_ids: list[str] = []
        now = datetime.now(UTC)

        for s_ref_id in source_ref_ids:
            # Retrieve media asset metadata if available
            media_asset = None
            try:
                media_asset = self.repository.get_media_asset(s_ref_id)
            except Exception:
                pass

            total_dur = media_asset.duration_seconds if media_asset and media_asset.duration_seconds else None
            recorded_at = media_asset.recorded_at if media_asset else None

            if recorded_at is not None:
                base_dt = recorded_at if recorded_at.tzinfo else recorded_at.replace(tzinfo=UTC)
            else:
                base_dt = datetime(1970, 1, 1, 0, 0, 0, tzinfo=UTC)

            # Filter artifacts strictly derived from this specific source media
            source_artifacts = [
                a
                for a in all_artifacts
                if a.source_reference and a.source_reference.media_asset_id == s_ref_id
            ]

            # Case: No artifacts examined for this source
            if not source_artifacts:
                cov_id = f"cov-{uuid.uuid4().hex[:8]}"
                end_dt = base_dt + timedelta(seconds=total_dur) if total_dur and total_dur > 0 else base_dt + timedelta(seconds=1.0)
                rec = CoverageRecord(
                    coverage_id=cov_id,
                    investigation_id=investigation_id,
                    source_reference_id=s_ref_id,
                    status=CoverageStatus.NOT_EXAMINED,
                    interval_start=base_dt,
                    interval_end=end_dt,
                    examined_at=None,
                    notes=f"No frames or audio examined for source '{s_ref_id}' (0.0% coverage).",
                    artifact_ids=[],
                )
                self.repository.add_coverage_record(rec)
                output_coverage_ids.append(cov_id)
                continue

            # Extract and merge examined intervals
            raw_intervals: list[tuple[float, float]] = []
            for art in source_artifacts:
                sr = art.source_reference
                if sr and sr.start_seconds is not None and sr.end_seconds is not None and sr.end_seconds > sr.start_seconds:
                    raw_intervals.append((sr.start_seconds, sr.end_seconds))

            raw_intervals.sort(key=lambda iv: iv[0])
            merged_intervals: list[tuple[float, float]] = []
            for s, e in raw_intervals:
                if not merged_intervals:
                    merged_intervals.append((s, e))
                else:
                    prev_s, prev_e = merged_intervals[-1]
                    if s <= prev_e:
                        merged_intervals[-1] = (prev_s, max(prev_e, e))
                    else:
                        merged_intervals.append((s, e))

            total_examined_sec = sum(e - s for s, e in merged_intervals)
            if total_dur is not None and total_dur > 0:
                coverage_pct = min(100.0, (total_examined_sec / total_dur) * 100.0)
            else:
                coverage_pct = 100.0 if merged_intervals else 0.0

            is_full_coverage = coverage_pct >= 95.0 or total_dur is None
            status = CoverageStatus.EXAMINED if is_full_coverage else CoverageStatus.PARTIAL

            # Record examined intervals
            for s_sec, e_sec in merged_intervals:
                cov_id = f"cov-{uuid.uuid4().hex[:8]}"
                int_artifacts = [
                    a.artifact_id
                    for a in source_artifacts
                    if a.source_reference
                    and a.source_reference.start_seconds >= s_sec - 0.001
                    and a.source_reference.end_seconds <= e_sec + 0.001
                ]
                assigned_art_ids = int_artifacts if int_artifacts else [a.artifact_id for a in source_artifacts]

                if total_dur is not None and total_dur > 0:
                    notes_text = (
                        f"Examined {s_sec:.1f}s-{e_sec:.1f}s of {total_dur:.1f}s "
                        f"({coverage_pct:.1f}% total footage coverage) for source '{s_ref_id}'."
                    )
                else:
                    notes_text = (
                        f"Examined timeline interval {s_sec:.1f}s-{e_sec:.1f}s for source '{s_ref_id}'."
                    )

                rec = CoverageRecord(
                    coverage_id=cov_id,
                    investigation_id=investigation_id,
                    source_reference_id=s_ref_id,
                    status=status,
                    interval_start=base_dt + timedelta(seconds=s_sec),
                    interval_end=base_dt + timedelta(seconds=e_sec),
                    examined_at=now,
                    notes=notes_text,
                    artifact_ids=assigned_art_ids,
                )
                self.repository.add_coverage_record(rec)
                output_coverage_ids.append(cov_id)

            # Detect and record unexamined gaps if total_dur is known and coverage is partial
            if total_dur is not None and total_dur > 0 and not is_full_coverage:
                gaps: list[tuple[float, float]] = []
                # Leading gap
                if merged_intervals and merged_intervals[0][0] > 0.5:
                    gaps.append((0.0, merged_intervals[0][0]))

                # Intermediary gaps
                for i in range(len(merged_intervals) - 1):
                    gap_s = merged_intervals[i][1]
                    gap_e = merged_intervals[i + 1][0]
                    if gap_e - gap_s > 0.5:
                        gaps.append((gap_s, gap_e))

                # Trailing gap
                if merged_intervals and total_dur - merged_intervals[-1][1] > 0.5:
                    gaps.append((merged_intervals[-1][1], total_dur))

                for gap_s, gap_e in gaps:
                    gap_cov_id = f"cov-gap-{uuid.uuid4().hex[:8]}"
                    gap_pct = ((gap_e - gap_s) / total_dur) * 100.0
                    gap_rec = CoverageRecord(
                        coverage_id=gap_cov_id,
                        investigation_id=investigation_id,
                        source_reference_id=s_ref_id,
                        status=CoverageStatus.NOT_EXAMINED,
                        interval_start=base_dt + timedelta(seconds=gap_s),
                        interval_end=base_dt + timedelta(seconds=gap_e),
                        examined_at=None,
                        notes=(
                            f"Unexamined timeline gap: {gap_s:.1f}s-{gap_e:.1f}s "
                            f"({gap_pct:.1f}% unexamined) for source '{s_ref_id}'."
                        ),
                        artifact_ids=[],
                    )
                    self.repository.add_coverage_record(gap_rec)
                    output_coverage_ids.append(gap_cov_id)

        return output_coverage_ids
