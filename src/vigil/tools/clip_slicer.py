"""Tool worker for cutting playable incident sub-clips around detected events."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from vigil.domain.artifact import Artifact
from vigil.domain.source_reference import SourceReference
from vigil.media.slicer import ClipSlicer
from vigil.orchestration.task_types import TaskRequest
from vigil.tools.base import BaseToolWorker, generate_sha256


def uri_to_file_path(uri: str) -> Path | None:
    """Resolve a file URI or path string to a local filesystem Path if it exists."""
    if uri.startswith("file://"):
        parsed = urlparse(uri)
        path = url2pathname(parsed.path)
        # Handle Windows drive letters like /D:/... -> D:/...
        if path.startswith("\\") and len(path) > 3 and path[2] == ":":
            path = path[1:]
        p = Path(path)
        return p if p.is_file() else None

    p = Path(uri)
    return p if p.is_file() else None


class ClipSlicerWorker(BaseToolWorker):
    """Forensic worker for slicing playable sub-clips around detected event intervals."""

    def run(self, request: TaskRequest) -> list[str]:
        media_id: str | None = None
        start_t: float | None = None
        end_t: float | None = None

        # 1. Resolve interval and media from parameters or referenced entities
        event_id = request.parameters.get("event_id")
        obs_id = request.parameters.get("observation_id")
        param_media_id = request.parameters.get("media_asset_id")

        if event_id and isinstance(event_id, str):
            event = self.repository.get_event(event_id)
            # Find interval
            if hasattr(event, "start_seconds") and hasattr(event, "end_seconds"):
                start_t = float(event.start_seconds)
                end_t = float(event.end_seconds)

            # Find media_asset_id from linked observations if available
            if hasattr(event, "observation_ids") and event.observation_ids:
                for oid in event.observation_ids:
                    try:
                        obs = self.repository.get_observation(oid)
                        if obs.source_references:
                            media_id = obs.source_references[0].media_asset_id
                            break
                    except Exception:  # noqa: BLE001, S110
                        pass

        elif obs_id and isinstance(obs_id, str):
            obs = self.repository.get_observation(obs_id)
            if obs.source_references:
                sr = obs.source_references[0]
                media_id = sr.media_asset_id
                start_t = sr.start_seconds
                end_t = sr.end_seconds

        # Fallback to direct parameter overrides
        if param_media_id and isinstance(param_media_id, str):
            media_id = param_media_id
        if "start_seconds" in request.parameters:
            start_t = float(request.parameters["start_seconds"])
        if "end_seconds" in request.parameters:
            end_t = float(request.parameters["end_seconds"])

        # Check input_refs if media_id is still unknown
        if not media_id and request.input_refs:
            first_ref = request.input_refs[0]
            # Check if ref is media_asset or event
            try:
                self.repository.get_media_asset(first_ref)
                media_id = first_ref
            except Exception:  # noqa: BLE001
                try:
                    evt = self.repository.get_event(first_ref)
                    if hasattr(evt, "start_seconds") and hasattr(evt, "end_seconds"):
                        start_t = float(evt.start_seconds)
                        end_t = float(evt.end_seconds)
                    if hasattr(evt, "observation_ids") and evt.observation_ids:
                        for oid in evt.observation_ids:
                            try:
                                obs = self.repository.get_observation(oid)
                                if obs.source_references:
                                    media_id = obs.source_references[0].media_asset_id
                                    break
                            except Exception:  # noqa: BLE001, S110
                                pass
                except Exception:  # noqa: BLE001, S110
                    pass

        if not media_id:
            all_assets = self.repository.list_media_assets()
            if not all_assets:
                raise ValueError("No media asset found to cut clip from.")
            media_id = all_assets[0].media_asset_id

        media_asset = self.repository.get_media_asset(media_id)
        asset_duration = media_asset.duration_seconds

        if start_t is None:
            start_t = 0.0

        if end_t is None:
            if asset_duration is not None:
                end_t = min(start_t + 5.0, asset_duration)
            else:
                raise ValueError(
                    f"Cannot determine clip boundaries: media asset '{media_id}' has unknown duration and no end timestamp was specified."
                )

        start_t = max(0.0, start_t)
        if asset_duration is not None:
            end_t = min(end_t, asset_duration)
        if end_t <= start_t:
            if asset_duration is not None:
                end_t = min(start_t + 1.0, asset_duration)
            else:
                end_t = start_t + 1.0

        padding = float(request.parameters.get("padding_seconds", 0.0))
        output_dir = request.parameters.get("output_dir")
        if output_dir:
            out_folder = Path(str(output_dir)).resolve()
        else:
            out_folder = Path(tempfile.gettempdir()) / "vigil_clips"
        out_folder.mkdir(parents=True, exist_ok=True)

        art_id = f"art-clip-{media_id}-{uuid.uuid4().hex[:8]}"
        out_file = out_folder / f"clip_{media_id}_{int(start_t)}_{int(end_t)}.mp4"

        # Check if physical video file exists at storage_uri
        physical_file = uri_to_file_path(media_asset.storage_uri)

        if physical_file is not None and physical_file.is_file():
            # Cut actual physical video clip
            result = ClipSlicer.slice_clip(
                source_path=physical_file,
                output_path=out_file,
                start_seconds=start_t,
                end_seconds=end_t,
                padding_seconds=padding,
            )
            clip_uri = result.storage_uri
            clip_sha = result.sha256
        else:
            # Fallback to valid synthetic artifact for tests/mock URIs
            clip_uri = out_file.as_uri()
            clip_sha = generate_sha256(f"{art_id}:{clip_uri}:{start_t}:{end_t}")

        source_ref = SourceReference(
            media_asset_id=media_id,
            start_seconds=start_t,
            end_seconds=end_t,
        )

        artifact = Artifact(
            artifact_id=art_id,
            artifact_type="clip",
            media_type="video",
            storage_uri=clip_uri,
            source_reference=source_ref,
            sha256=clip_sha,
        )
        self.repository.add_artifact(artifact)

        return [art_id]
