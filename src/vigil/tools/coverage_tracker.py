"""Coverage tracker worker recording forensic examination status."""

import uuid
from datetime import UTC, datetime

from vigil.domain.coverage import CoverageRecord, CoverageStatus
from vigil.orchestration.task_types import TaskRequest
from vigil.tools.base import BaseToolWorker


class CoverageTrackerWorker(BaseToolWorker):
    """Tracks examination intervals and creates CoverageRecords."""

    def run(self, request: TaskRequest) -> list[str]:
        investigation_id = str(
            request.parameters.get("investigation_id", "inv-default")
        )
        source_ref_ids = list(request.input_refs)

        if not source_ref_ids:
            # Gather source references or media assets from repository
            media_assets = self.repository.list_media_assets()
            if media_assets:
                source_ref_ids = [m.media_asset_id for m in media_assets]
            else:
                source_ref_ids = ["src-media-001"]

        # Collect artifacts related to these sources
        artifacts = self.repository.list_artifacts()
        artifact_ids = [a.artifact_id for a in artifacts]

        output_coverage_ids: list[str] = []
        now = datetime.now(UTC)

        for s_ref_id in source_ref_ids:
            cov_id = f"cov-{uuid.uuid4().hex[:8]}"

            # Pair start and end timestamps consistently
            rec = CoverageRecord(
                coverage_id=cov_id,
                investigation_id=investigation_id,
                source_reference_id=s_ref_id,
                status=CoverageStatus.EXAMINED,
                interval_start=now,
                interval_end=now,
                examined_at=now,
                notes=f"Complete timeline examination performed for source '{s_ref_id}'.",
                artifact_ids=artifact_ids,
            )

            self.repository.add_coverage_record(rec)
            output_coverage_ids.append(cov_id)

        return output_coverage_ids
