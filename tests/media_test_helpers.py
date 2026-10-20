"""Test helpers for generating real physical media files for testing."""

from __future__ import annotations

import math
import wave
from pathlib import Path

import av
import numpy as np


def create_test_video(
    path: Path | str,
    duration_seconds: float = 2.0,
    fps: int = 24,
    width: int = 320,
    height: int = 240,
    with_audio: bool = True,
) -> Path:
    """Generate a valid MP4 test video with visual motion and synthetic audio."""
    file_path = Path(path).resolve()
    file_path.parent.mkdir(parents=True, exist_ok=True)

    total_frames = int(duration_seconds * fps)

    with av.open(str(file_path), mode="w", format="mp4") as container:
        v_stream = container.add_stream("h264", rate=fps)
        v_stream.width = width
        v_stream.height = height
        v_stream.pix_fmt = "yuv420p"

        a_stream = None
        if with_audio:
            try:
                a_stream = container.add_stream("aac", rate=44100)
                a_stream.format = "fltp"
                a_stream.layout = "stereo"
            except Exception:  # noqa: BLE001
                a_stream = None

        # Write video frames
        for i in range(total_frames):
            img = np.zeros((height, width, 3), dtype=np.uint8)
            # Add dynamic colored pattern
            img[:, :, 0] = (i * 10) % 255
            img[:, :, 1] = 120
            img[:, :, 2] = 200
            frame = av.VideoFrame.from_ndarray(img, format="bgr24")
            for packet in v_stream.encode(frame):
                container.mux(packet)

        # Write audio samples if stream initialized
        if a_stream is not None:
            num_samples = int(duration_seconds * 44100)
            t = np.linspace(0, duration_seconds, num_samples, dtype=np.float32)
            sine = np.sin(2 * math.pi * 440 * t)
            stereo_audio = np.stack([sine, sine])
            a_frame = av.AudioFrame.from_ndarray(stereo_audio, format="fltp", layout="stereo")
            a_frame.rate = 44100
            for packet in a_stream.encode(a_frame):
                container.mux(packet)
            for packet in a_stream.encode():
                container.mux(packet)

        for packet in v_stream.encode():
            container.mux(packet)

    return file_path


def create_test_wav(
    path: Path | str,
    duration_seconds: float = 2.0,
    sample_rate: int = 16000,
    frequency: float = 440.0,
) -> Path:
    """Generate a standard 16-bit PCM WAV audio file."""
    file_path = Path(path).resolve()
    file_path.parent.mkdir(parents=True, exist_ok=True)

    num_samples = int(duration_seconds * sample_rate)
    t = np.linspace(0, duration_seconds, num_samples, dtype=np.float32)
    sine = (np.sin(2 * math.pi * frequency * t) * 32767).astype(np.int16)

    with wave.open(str(file_path), "wb") as wf:
        wf.setnchannels(1)  # Mono
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(sine.tobytes())

    return file_path
