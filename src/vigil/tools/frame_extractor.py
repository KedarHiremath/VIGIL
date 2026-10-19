"""Tool worker for media frame extraction and interval sampling."""

import uuid

from vigil.domain.artifact import Artifact
from vigil.domain.source_reference import SourceReference
from vigil.orchestration.task_types import TaskRequest
from vigil.tools.base import BaseToolWorker, generate_sha256


class FrameExtractorWorker(BaseToolWorker):
    """Samples video frames and creates derived Artifact records."""

    def run(self, request: TaskRequest) -> list[str]:
        # Identify target media assets
        media_ids = list(request.input_refs)
        param_media_id = request.parameters.get("media_asset_id")
        if param_media_id and isinstance(param_media_id, str):
            media_ids.append(param_media_id)

        if not media_ids:
            # Fall back to inspecting repository for available assets
            all_assets = self.repository.list_media_assets()
            if not all_assets:
                raise ValueError("No media assets provided or available in repository.")
            media_ids = [all_assets[0].media_asset_id]

        sample_interval = float(request.parameters.get("sample_interval_seconds", 2.0))
        max_frames = int(request.parameters.get("max_frames", 10))
        frame_duration = float(request.parameters.get("frame_duration", 0.5))

        output_artifact_ids: list[str] = []

        for media_id in media_ids:
            media_asset = self.repository.get_media_asset(media_id)
            duration = media_asset.duration_seconds or 30.0

            start_t = float(request.parameters.get("start_seconds", 0.0))
            end_t = float(request.parameters.get("end_seconds", duration))
            end_t = min(end_t, duration)

            current_t = start_t
            frame_idx = 0

            while current_t < end_t and frame_idx < max_frames:
                frame_end = min(current_t + frame_duration, duration)
                if frame_end <= current_t:
                    frame_end = current_t + 0.1

                source_ref = SourceReference(
                    media_asset_id=media_id,
                    start_seconds=current_t,
                    end_seconds=frame_end,
                )

                art_id = f"art-{media_id}-f{frame_idx}-{uuid.uuid4().hex[:6]}"
                storage_uri = (
                    f"file:///storage/artifacts/{media_id}/frame_{frame_idx:04d}.jpg"
                )
                sha256 = generate_sha256(f"{art_id}:{storage_uri}:{current_t}")

                artifact = Artifact(
                    artifact_id=art_id,
                    artifact_type="frame",
                    media_type="image",
                    storage_uri=storage_uri,
                    source_reference=source_ref,
                    sha256=sha256,
                )

                self.repository.add_artifact(artifact)
                output_artifact_ids.append(art_id)

                current_t += sample_interval
                frame_idx += 1

        return output_artifact_ids
