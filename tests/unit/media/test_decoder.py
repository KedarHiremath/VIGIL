"""Unit tests for physical media decoding, JPEG extraction, and WAV demuxing."""

from pathlib import Path

import pytest

from tests.media_test_helpers import create_test_video
from vigil.media.decoder import MediaDecoder


def test_extract_frames_from_video(tmp_path: Path) -> None:
    video_path = tmp_path / "test_extract.mp4"
    create_test_video(video_path, duration_seconds=2.0, fps=24, width=320, height=240)

    out_frames_dir = tmp_path / "frames"
    frames = MediaDecoder.extract_frames(
        file_path=video_path,
        output_dir=out_frames_dir,
        sample_interval_seconds=0.5,
        max_frames=5,
    )

    assert len(frames) > 0
    assert len(frames) <= 5

    for f in frames:
        assert Path(f.file_path).is_file()
        assert f.width == 320
        assert f.height == 240
        assert len(f.sha256) == 64
        assert f.timestamp_seconds >= 0.0


def test_demux_audio_to_wav(tmp_path: Path) -> None:
    video_path = tmp_path / "test_demux.mp4"
    create_test_video(video_path, duration_seconds=1.5, with_audio=True)

    wav_out = tmp_path / "audio" / "extracted.wav"
    demuxed = MediaDecoder.demux_audio_to_wav(
        file_path=video_path,
        output_path=wav_out,
        target_sample_rate=16000,
    )

    assert Path(demuxed.file_path).is_file()
    assert demuxed.sample_rate == 16000
    assert demuxed.channels in {1, 2}
    assert demuxed.duration_seconds > 0.0
    assert len(demuxed.sha256) == 64


def test_demux_audio_on_video_without_audio_raises(tmp_path: Path) -> None:
    silent_video = tmp_path / "silent.mp4"
    create_test_video(silent_video, duration_seconds=1.0, with_audio=False)

    wav_out = tmp_path / "silent.wav"
    with pytest.raises(ValueError, match="No audio stream found"):
        MediaDecoder.demux_audio_to_wav(
            file_path=silent_video,
            output_path=wav_out,
        )


def test_decoder_non_existent_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        MediaDecoder.extract_frames("missing.mp4", "output")
