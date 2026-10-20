"""Incident clip cutting tool for extracting playable video sub-clips."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import av
import cv2


@dataclass(frozen=True)
class SliceResult:
    """Represents an extracted incident video sub-clip."""

    clip_path: str
    storage_uri: str
    sha256: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    width: int
    height: int
    fps: float


class ClipSlicer:
    """Slices video intervals ([start_seconds, end_seconds)) into playable MP4 clips."""

    @staticmethod
    def _compute_sha256(path: Path) -> str:
        hasher = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @classmethod
    def slice_clip(
        cls,
        source_path: str | Path,
        output_path: str | Path,
        start_seconds: float,
        end_seconds: float,
        padding_seconds: float = 0.0,
    ) -> SliceResult:
        """Cut a playable MP4 sub-clip between start_seconds and end_seconds."""
        src = Path(source_path).resolve()
        if not src.is_file():
            raise FileNotFoundError(f"Source video file not found: {src}")

        if start_seconds < 0:
            raise ValueError(f"start_seconds must be non-negative, got {start_seconds}")
        if end_seconds <= start_seconds:
            raise ValueError(
                f"end_seconds ({end_seconds}) must be strictly greater than start_seconds ({start_seconds})"
            )

        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        eff_start = max(0.0, start_seconds - padding_seconds)
        eff_end = end_seconds + padding_seconds

        # Attempt slicing with PyAV for full audio+video encoding
        try:
            with av.open(str(src)) as in_container:
                if len(in_container.streams.video) == 0:
                    raise ValueError(f"No video stream found in {src}")

                in_video = in_container.streams.video[0]
                fps = (
                    float(in_video.average_rate)
                    if in_video.average_rate and float(in_video.average_rate) > 0
                    else 24.0
                )
                width = in_video.width
                height = in_video.height
                v_time_base = float(in_video.time_base) if in_video.time_base else 1.0 / fps

                has_audio = len(in_container.streams.audio) > 0
                in_audio = in_container.streams.audio[0] if has_audio else None

                with av.open(str(out), mode="w", format="mp4") as out_container:
                    out_video = out_container.add_stream("h264", rate=round(fps))
                    out_video.width = width
                    out_video.height = height
                    out_video.pix_fmt = "yuv420p"

                    out_audio = None
                    if in_audio is not None:
                        try:
                            out_audio = out_container.add_stream("aac", rate=in_audio.rate or 44100)
                            out_audio.format = "fltp"
                            out_audio.layout = "stereo" if in_audio.channels == 2 else "mono"
                        except Exception:  # noqa: BLE001
                            out_audio = None

                    # Decode and write video
                    frame_count = 0
                    for frame in in_container.decode(in_video):
                        pts = frame.pts
                        t = float(pts * v_time_base) if pts is not None else (frame_count / fps)
                        if t < eff_start:
                            continue
                        if t >= eff_end:
                            break

                        # Re-encode video frame
                        for packet in out_video.encode(frame):
                            out_container.mux(packet)
                        frame_count += 1

                    for packet in out_video.encode():
                        out_container.mux(packet)

                    # Audio slicing if available
                    if in_audio is not None and out_audio is not None:
                        a_time_base = float(in_audio.time_base) if in_audio.time_base else 1.0 / 44100
                        try:
                            in_container.seek(0)
                            for a_frame in in_container.decode(in_audio):
                                a_pts = a_frame.pts
                                a_t = float(a_pts * a_time_base) if a_pts is not None else 0.0
                                if a_t < eff_start:
                                    continue
                                if a_t >= eff_end:
                                    break
                                for packet in out_audio.encode(a_frame):
                                    out_container.mux(packet)
                            for packet in out_audio.encode():
                                out_container.mux(packet)
                        except Exception:  # noqa: BLE001, S110
                            pass

                if out.is_file() and out.stat().st_size > 0:
                    sha256_sum = cls._compute_sha256(out)
                    actual_duration = frame_count / fps if fps > 0 else (eff_end - eff_start)
                    return SliceResult(
                        clip_path=str(out),
                        storage_uri=out.as_uri(),
                        sha256=sha256_sum,
                        start_seconds=round(eff_start, 3),
                        end_seconds=round(eff_end, 3),
                        duration_seconds=round(actual_duration, 3),
                        width=width,
                        height=height,
                        fps=round(fps, 3),
                    )
        except Exception:  # noqa: BLE001, S110
            # Fall back to OpenCV VideoWriter
            pass

        # OpenCV Fallback
        cap = cv2.VideoCapture(str(src))
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video file with OpenCV: {src}")

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        start_frame = int(eff_start * fps)
        end_frame = int(eff_end * fps)
        if total_frames > 0:
            end_frame = min(end_frame, total_frames)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out), fourcc, fps, (width, height))

        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        written_frames = 0

        for _ in range(start_frame, end_frame):
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            writer.write(frame)
            written_frames += 1

        writer.release()
        cap.release()

        if not out.is_file() or out.stat().st_size == 0:
            raise RuntimeError(f"Clip generation failed, empty output at {out}")

        sha256_sum = cls._compute_sha256(out)
        actual_duration = written_frames / fps if fps > 0 else (eff_end - eff_start)

        return SliceResult(
            clip_path=str(out),
            storage_uri=out.as_uri(),
            sha256=sha256_sum,
            start_seconds=round(eff_start, 3),
            end_seconds=round(eff_end, 3),
            duration_seconds=round(actual_duration, 3),
            width=width,
            height=height,
            fps=round(fps, 3),
        )
