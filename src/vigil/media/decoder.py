"""Physical video and audio decoding, JPEG extraction, and WAV demuxing."""

from __future__ import annotations

import hashlib
import logging
import wave
from dataclasses import dataclass
from pathlib import Path

import av
import cv2

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractedFrame:
    """Represents an extracted physical JPEG image frame."""

    frame_index: int
    timestamp_seconds: float
    file_path: str
    storage_uri: str
    sha256: str
    width: int
    height: int


@dataclass(frozen=True)
class DemuxedAudio:
    """Represents a demuxed WAV audio file."""

    file_path: str
    storage_uri: str
    sha256: str
    duration_seconds: float
    sample_rate: int
    channels: int


class MediaDecoder:
    """Decodes video files (.mp4, .mkv, .avi) to JPEG frames and demuxes audio tracks to WAV."""

    @staticmethod
    def _compute_sha256_bytes(data: bytes) -> str:
        """Compute SHA-256 checksum from bytes."""
        return hashlib.sha256(data).hexdigest()

    @classmethod
    def _compute_sha256_file(cls, path: Path) -> str:
        """Compute SHA-256 checksum from file."""
        hasher = hashlib.sha256()
        with path.open("rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()

    @classmethod
    def extract_frames(
        cls,
        file_path: str | Path,
        output_dir: str | Path,
        sample_interval_seconds: float = 2.0,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
        max_frames: int = 100,
        jpeg_quality: int = 95,
    ) -> list[ExtractedFrame]:
        """Decode video frames at intervals and write actual JPEG files to disk.

        Spreads samples across [start, end] when the cap is reached instead of truncating the tail.
        Seeks directly when start_seconds > 0.
        """
        src_path = Path(file_path).resolve()
        if not src_path.is_file():
            raise FileNotFoundError(f"Media file does not exist: {src_path}")

        out_path = Path(output_dir).resolve()
        out_path.mkdir(parents=True, exist_ok=True)

        extracted: list[ExtractedFrame] = []
        interval = max(0.001, sample_interval_seconds)

        # Attempt extraction via PyAV
        try:
            with av.open(str(src_path)) as container:
                if len(container.streams.video) == 0:
                    return []

                stream = container.streams.video[0]
                time_base = float(stream.time_base) if stream.time_base else 1.0 / 24.0

                stream_duration = (
                    float(stream.duration * stream.time_base)
                    if stream.duration is not None and stream.time_base
                    else None
                )
                container_duration = (
                    float(container.duration) / float(av.time_base)
                    if container.duration
                    else None
                )
                total_duration = stream_duration or container_duration

                if end_seconds is not None:
                    stop_at = min(end_seconds, total_duration) if total_duration is not None else end_seconds
                else:
                    stop_at = total_duration

                # Adapt interval to spread frames across [start, end] if cap would be exceeded
                if stop_at is not None and stop_at > start_seconds and max_frames > 0:
                    timeline_span = stop_at - start_seconds
                    expected_count = timeline_span / interval
                    if expected_count > max_frames:
                        interval = timeline_span / max_frames

                # Seek directly to start timestamp if start_seconds > 0
                if start_seconds > 0:
                    try:
                        seek_pts = int(start_seconds / time_base)
                        container.seek(seek_pts, stream=stream, backward=True)
                    except Exception as seek_exc:
                        logger.debug("PyAV stream seek failed (%s); continuing from stream start.", seek_exc)

                stream_start_pts = stream.start_time if stream.start_time is not None else 0
                stream_start_sec = float(stream_start_pts * time_base)

                next_target_t = max(0.0, start_seconds)
                frame_idx = 0

                for frame in container.decode(stream):
                    if frame_idx >= max_frames:
                        break

                    pts = frame.pts
                    if pts is not None:
                        current_t = float(pts * time_base) - stream_start_sec
                    else:
                        current_t = start_seconds + (frame_idx * interval)

                    if current_t < next_target_t:
                        continue
                    if stop_at is not None and current_t > stop_at:
                        break

                    # Convert PyAV VideoFrame to numpy BGR for OpenCV JPEG encoding
                    img_bgr = frame.to_ndarray(format="bgr24")
                    h, w = img_bgr.shape[:2]

                    # Filename embeds timestamp in milliseconds
                    file_name = f"frame_{int(round(max(0.0, current_t) * 1000)):09d}.jpg"
                    jpeg_path = out_path / file_name

                    # Encode to JPEG
                    success, enc_buf = cv2.imencode(
                        ".jpg",
                        img_bgr,
                        [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality],
                    )
                    if not success:
                        continue

                    raw_bytes = enc_buf.tobytes()
                    jpeg_path.write_bytes(raw_bytes)
                    sha256_sum = cls._compute_sha256_bytes(raw_bytes)

                    extracted.append(
                        ExtractedFrame(
                            frame_index=frame_idx,
                            timestamp_seconds=round(max(0.0, current_t), 3),
                            file_path=str(jpeg_path),
                            storage_uri=jpeg_path.as_uri(),
                            sha256=sha256_sum,
                            width=w,
                            height=h,
                        )
                    )

                    frame_idx += 1
                    next_target_t = current_t + interval

            if extracted:
                return extracted
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "PyAV frame extraction failed for %s (%s); falling back to OpenCV VideoCapture.",
                src_path,
                exc,
            )
            extracted = []

        # OpenCV Fallback
        extracted = []
        cap = cv2.VideoCapture(str(src_path))
        if not cap.isOpened():
            return []

        fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 and total_frames > 0 else None

        if end_seconds is not None:
            stop_t = min(end_seconds, duration) if duration is not None else end_seconds
        else:
            stop_t = duration

        cv_interval = max(0.001, sample_interval_seconds)
        if stop_t is not None and stop_t > start_seconds and max_frames > 0:
            timeline_span = stop_t - start_seconds
            if (timeline_span / cv_interval) > max_frames:
                cv_interval = timeline_span / max_frames

        next_t = max(0.0, start_seconds)
        frame_idx = 0

        while frame_idx < max_frames:
            if stop_t is not None and next_t > stop_t:
                break

            target_frame_num = int(next_t * fps)
            if total_frames > 0 and target_frame_num >= total_frames:
                break

            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame_num)
            ret, img_bgr = cap.read()
            if not ret or img_bgr is None:
                break

            actual_pos_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
            actual_t = actual_pos_msec / 1000.0 if actual_pos_msec > 0 else next_t

            if stop_t is not None and actual_t > stop_t:
                break

            h, w = img_bgr.shape[:2]
            jpeg_path = out_path / f"frame_{int(round(max(0.0, actual_t) * 1000)):09d}.jpg"
            success, enc_buf = cv2.imencode(
                ".jpg",
                img_bgr,
                [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality],
            )
            if success:
                raw_bytes = enc_buf.tobytes()
                jpeg_path.write_bytes(raw_bytes)
                sha256_sum = cls._compute_sha256_bytes(raw_bytes)

                extracted.append(
                    ExtractedFrame(
                        frame_index=frame_idx,
                        timestamp_seconds=round(max(0.0, actual_t), 3),
                        file_path=str(jpeg_path),
                        storage_uri=jpeg_path.as_uri(),
                        sha256=sha256_sum,
                        width=w,
                        height=h,
                    )
                )
                frame_idx += 1

            next_t += cv_interval

        cap.release()
        return extracted

    @classmethod
    def demux_audio_to_wav(
        cls,
        file_path: str | Path,
        output_path: str | Path,
        start_seconds: float = 0.0,
        end_seconds: float | None = None,
        target_sample_rate: int = 16000,
        mono: bool = False,
    ) -> DemuxedAudio:
        """Demux audio track from a video/audio file and write standard 16-bit PCM WAV."""
        src_path = Path(file_path).resolve()
        if not src_path.is_file():
            raise FileNotFoundError(f"Media file does not exist: {src_path}")

        wav_path = Path(output_path).resolve()
        wav_path.parent.mkdir(parents=True, exist_ok=True)

        layout = "mono" if mono else "stereo"
        channels = 1 if mono else 2

        with av.open(str(src_path)) as container:
            if len(container.streams.audio) == 0:
                raise ValueError(f"No audio stream found in media file: {src_path}")

            stream = container.streams.audio[0]
            resampler = av.AudioResampler(
                format="s16",
                layout=layout,
                rate=target_sample_rate,
            )

            time_base = float(stream.time_base) if stream.time_base else 1.0 / stream.rate
            audio_chunks: list[bytes] = []
            total_samples = 0

            for frame in container.decode(stream):
                pts = frame.pts
                frame_t = float(pts * time_base) if pts is not None else 0.0

                if end_seconds is not None and frame_t > end_seconds:
                    break
                if frame_t + (float(frame.samples) / stream.rate) < start_seconds:
                    continue

                resampled = resampler.resample(frame)
                if resampled:
                    for r_frame in resampled:
                        data = r_frame.to_ndarray().tobytes()
                        audio_chunks.append(data)
                        total_samples += r_frame.samples

        # Write WAV file using Python standard wave module
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(target_sample_rate)
            wf.writeframes(b"".join(audio_chunks))

        duration_sec = total_samples / float(target_sample_rate) if target_sample_rate > 0 else 0.0
        sha256_sum = cls._compute_sha256_file(wav_path)

        return DemuxedAudio(
            file_path=str(wav_path),
            storage_uri=wav_path.as_uri(),
            sha256=sha256_sum,
            duration_seconds=round(duration_sec, 3),
            sample_rate=target_sample_rate,
            channels=channels,
        )
