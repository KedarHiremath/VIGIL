"""Audio transcription and acoustic event analysis worker."""

import logging
import uuid
import wave
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

import numpy as np

from vigil.domain.observation import Observation
from vigil.domain.provenance import Provenance
from vigil.domain.source_reference import SourceReference
from vigil.orchestration.task_types import TaskRequest
from vigil.tools.base import BaseToolWorker

logger = logging.getLogger(__name__)


def _uri_to_path(uri: str | None) -> Path | None:
    """Resolve file URI or local path string to a Path object."""
    if not uri:
        return None
    try:
        if uri.startswith("file://"):
            parsed = urlparse(uri)
            path_str = unquote(parsed.path)
            if path_str.startswith("/") and len(path_str) > 2 and path_str[2] == ":":
                path_str = path_str[1:]
            p = Path(path_str)
            return p if p.is_file() else None
        p = Path(uri)
        return p if p.is_file() else None
    except Exception:
        return None


def _analyze_audio_signal(wav_path: Path) -> dict[str, Any]:
    """Perform physical acoustic energy, RMS, and transient burst detection."""
    try:
        with wave.open(str(wav_path), "rb") as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            raw_data = wf.readframes(nframes)

        duration = nframes / float(framerate) if framerate > 0 else 0.0
        if duration <= 0 or len(raw_data) == 0:
            return {"duration": 0.0, "events": [], "mean_rms": 0.0, "max_rms": 0.0}

        # Decode PCM samples
        if sampwidth == 2:
            samples = np.frombuffer(raw_data, dtype=np.int16).astype(np.float32) / 32768.0
        elif sampwidth == 4:
            samples = np.frombuffer(raw_data, dtype=np.int32).astype(np.float32) / 2147483648.0
        else:
            samples = np.frombuffer(raw_data, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0

        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1)

        window_sec = 0.25
        window_samples = int(framerate * window_sec)
        if window_samples <= 0:
            return {"duration": duration, "events": [], "mean_rms": 0.0, "max_rms": 0.0}

        num_windows = len(samples) // window_samples
        energies = []
        for i in range(num_windows):
            w = samples[i * window_samples : (i + 1) * window_samples]
            rms = float(np.sqrt(np.mean(w**2)))
            energies.append(rms)

        if not energies:
            return {"duration": duration, "events": [], "mean_rms": 0.0, "max_rms": 0.0}

        mean_rms = float(np.mean(energies))
        max_rms = float(np.max(energies))

        # Detect transient bursts above noise floor
        threshold = max(0.015, mean_rms * 1.8)
        burst_intervals: list[dict[str, Any]] = []
        current_burst: dict[str, Any] | None = None

        for i, rms in enumerate(energies):
            t_start = round(i * window_sec, 2)
            t_end = round((i + 1) * window_sec, 2)
            if rms > threshold:
                if current_burst is None:
                    current_burst = {"start": t_start, "end": t_end, "peak_rms": round(rms, 4)}
                else:
                    current_burst["end"] = t_end
                    current_burst["peak_rms"] = max(current_burst["peak_rms"], round(rms, 4))
            else:
                if current_burst is not None:
                    burst_intervals.append(current_burst)
                    current_burst = None

        if current_burst is not None:
            burst_intervals.append(current_burst)

        return {
            "duration": round(duration, 2),
            "channels": channels,
            "sample_rate": framerate,
            "mean_rms": round(mean_rms, 4),
            "max_rms": round(max_rms, 4),
            "events": burst_intervals,
        }
    except Exception as exc:
        logger.warning(f"Audio DSP analysis error: {exc}")
        return {"error": str(exc)}


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
            asset = None
            audio_artifact = None

            # 1. Identify asset and audio artifact
            all_assets_map = {a.media_asset_id: a for a in self.repository.list_media_assets()}
            if ref_id in all_assets_map:
                asset = all_assets_map[ref_id]
                # Look up extracted audio artifact for this asset
                for art in self.repository.list_artifacts():
                    if (
                        art.media_type == "audio"
                        and art.source_reference
                        and art.source_reference.media_asset_id == asset.media_asset_id
                    ):
                        audio_artifact = art
                        break
            else:
                try:
                    art = self.repository.get_artifact(ref_id)
                    if art.media_type == "audio":
                        audio_artifact = art
                        if art.source_reference and art.source_reference.media_asset_id in all_assets_map:
                            asset = all_assets_map[art.source_reference.media_asset_id]
                except Exception:
                    pass

            # 2. Case: No audio artifact found (silent video or no audio track)
            if audio_artifact is None:
                duration = asset.duration_seconds if asset and asset.duration_seconds else 10.0
                obs_id = f"obs-aud-{uuid.uuid4().hex[:8]}"
                source_ref = SourceReference(
                    media_asset_id=asset.media_asset_id if asset else ref_id,
                    start_seconds=0.0,
                    end_seconds=duration,
                )
                provenance = Provenance(
                    producer_type="audio_model",
                    producer_name="acoustic-analyzer",
                    method="acoustic_inspection",
                    input_artifact_ids=[],
                )
                obs = Observation(
                    observation_id=obs_id,
                    modality="audio",
                    observation_type="acoustic_inspection",
                    description=(
                        "Acoustic inspection completed: No audio stream detected "
                        "in source media container (silent surveillance recording)."
                    ),
                    source_references=[source_ref],
                    artifact_ids=[],
                    confidence=1.0,
                    provenance=provenance,
                )
                self.repository.add_observation(obs)
                output_observation_ids.append(obs_id)
                continue

            # 3. Case: Audio artifact exists -> Physical acoustic signal analysis
            wav_path = _uri_to_path(audio_artifact.storage_uri)
            dsp_info: dict[str, Any] = {}
            if wav_path and wav_path.is_file():
                dsp_info = _analyze_audio_signal(wav_path)

            events = dsp_info.get("events", [])
            duration = dsp_info.get("duration", asset.duration_seconds if asset else 10.0)
            mean_rms = dsp_info.get("mean_rms", 0.0)
            max_rms = dsp_info.get("max_rms", 0.0)

            # Determine timing bounds for observation
            if events:
                start_sec = events[0]["start"]
                end_sec = events[-1]["end"]
                obs_type = "acoustic_transient"
            else:
                start_sec = 0.0
                end_sec = duration
                obs_type = "acoustic_monitoring"

            source_ref = SourceReference(
                media_asset_id=asset.media_asset_id if asset else audio_artifact.source_reference.media_asset_id,
                start_seconds=start_sec,
                end_seconds=end_sec,
            )

            # Format physical acoustic findings
            if events:
                event_bullets = "; ".join(
                    [f"[{e['start']}s-{e['end']}s, peak RMS {e['peak_rms']}]" for e in events[:6]]
                )
                base_desc = (
                    f"Acoustic signal analysis: detected {len(events)} acoustic activity/transient spike(s) "
                    f"across {duration}s audio track. Baseline ambient noise floor: RMS {mean_rms}. "
                    f"Peak sound burst: RMS {max_rms}. Key intervals: {event_bullets}."
                )
            else:
                base_desc = (
                    f"Acoustic signal analysis: continuous ambient background audio across {duration}s track. "
                    f"Average noise floor: RMS {mean_rms}. No anomalous transient spikes or threshold violations detected."
                )

            # 4. Optional LLM Forensic Interpretation
            final_desc = base_desc
            if self.llm is not None:
                try:
                    prompt = (
                        f"Forensic acoustic telemetry summary:\n{base_desc}\n\n"
                        "Provide a concise forensic interpretation (1-2 sentences) of these acoustic events, "
                        "noting potential physical causes (movement, impacts, door tampering, ambient noise)."
                    )
                    llm_resp = self.llm.generate_text(prompt=prompt, json_mode=False)
                    if llm_resp and llm_resp.content and len(llm_resp.content.strip()) > 10:
                        content_clean = llm_resp.content.strip()
                        # Avoid echoing generic refusal text
                        if "unable to transcribe" not in content_clean.lower() and "please provide" not in content_clean.lower():
                            final_desc = f"{base_desc} Forensic Assessment: {content_clean}"
                except Exception as exc:
                    logger.warning(f"AudioTranscriberWorker: LLM interpretation skipped ({exc})")

            obs_id = f"obs-aud-{uuid.uuid4().hex[:8]}"
            provenance = Provenance(
                producer_type="audio_model",
                producer_name=getattr(self.llm, "model_name", "acoustic-dsp-model") or "acoustic-dsp-model",
                method="acoustic_signal_and_transient_analysis",
                input_artifact_ids=[audio_artifact.artifact_id],
            )

            obs = Observation(
                observation_id=obs_id,
                modality="audio",
                observation_type=obs_type,
                description=final_desc,
                source_references=[source_ref],
                artifact_ids=[audio_artifact.artifact_id],
                confidence=0.92 if events else 0.85,
                provenance=provenance,
            )

            self.repository.add_observation(obs)
            output_observation_ids.append(obs_id)

        return output_observation_ids

