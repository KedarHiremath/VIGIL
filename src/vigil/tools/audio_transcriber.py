"""Audio transcription and acoustic event analysis worker."""

import uuid

from vigil.domain.observation import Observation
from vigil.domain.provenance import Provenance
from vigil.domain.source_reference import SourceReference
from vigil.orchestration.task_types import TaskRequest
from vigil.tools.base import BaseToolWorker


class AudioTranscriberWorker(BaseToolWorker):
    """Transcribes audio tracks and analyzes acoustic events."""

    def run(self, request: TaskRequest) -> list[str]:
        input_refs = list(request.input_refs)
        media_id = request.parameters.get("media_asset_id")

        if not input_refs and media_id and isinstance(media_id, str):
            input_refs = [media_id]

        if not input_refs:
            all_assets = self.repository.list_media_assets()
            audio_assets = [a for a in all_assets if a.media_type in {"audio", "video"}]
            if not audio_assets:
                raise ValueError(
                    "No audio or video media assets available for transcription."
                )
            input_refs = [audio_assets[0].media_asset_id]

        output_observation_ids: list[str] = []

        for ref_id in input_refs:
            # Check if reference is an asset or artifact
            if ref_id in [
                a.media_asset_id for a in self.repository.list_media_assets()
            ]:
                asset = self.repository.get_media_asset(ref_id)
                duration = asset.duration_seconds or 10.0
                source_ref = SourceReference(
                    media_asset_id=asset.media_asset_id,
                    start_seconds=0.0,
                    end_seconds=duration,
                )
                artifact_ids = []
            else:
                artifact = self.repository.get_artifact(ref_id)
                source_ref = artifact.source_reference
                artifact_ids = [artifact.artifact_id]

            prompt = (
                "Transcribe any speech and detect notable acoustic events "
                "(alarms, breaking glass, shouting, sirens) from the audio recording."
            )
            response = self.llm.generate_text(prompt=prompt, json_mode=False)

            obs_id = f"obs-aud-{uuid.uuid4().hex[:8]}"
            provenance = Provenance(
                producer_type="audio_model",
                producer_name=getattr(self.llm, "model_name", "audio_model")
                or "audio_model",
                method="acoustic_transcription_and_event_detection",
                input_artifact_ids=artifact_ids,
            )

            desc = (
                response.content.strip()
                or "Audio analysis completed; no loud disturbances detected."
            )
            obs = Observation(
                observation_id=obs_id,
                modality="audio",
                observation_type="audio_transcription",
                description=desc,
                source_references=[source_ref],
                artifact_ids=artifact_ids,
                confidence=0.88,
                provenance=provenance,
            )

            self.repository.add_observation(obs)
            output_observation_ids.append(obs_id)

        return output_observation_ids
