"""Unit tests for incident clip cutting tool."""

from pathlib import Path

import pytest

from tests.media_test_helpers import create_test_video
from vigil.media.slicer import ClipSlicer


def test_slice_clip_valid_interval(tmp_path: Path) -> None:
    src_video = tmp_path / "long_source.mp4"
    create_test_video(src_video, duration_seconds=3.0, fps=24, width=320, height=240, with_audio=True)

    out_clip = tmp_path / "clips" / "incident_01.mp4"
    result = ClipSlicer.slice_clip(
        source_path=src_video,
        output_path=out_clip,
        start_seconds=0.5,
        end_seconds=2.0,
        padding_seconds=0.0,
    )

    assert Path(result.clip_path).is_file()
    assert result.duration_seconds > 0.5
    assert result.start_seconds == 0.5
    assert result.end_seconds == 2.0
    assert len(result.sha256) == 64
    assert result.width == 320
    assert result.height == 240


def test_slice_clip_with_padding(tmp_path: Path) -> None:
    src_video = tmp_path / "source.mp4"
    create_test_video(src_video, duration_seconds=3.0, fps=24)

    out_clip = tmp_path / "padded_clip.mp4"
    result = ClipSlicer.slice_clip(
        source_path=src_video,
        output_path=out_clip,
        start_seconds=1.0,
        end_seconds=2.0,
        padding_seconds=0.25,
    )

    assert Path(result.clip_path).is_file()
    assert result.start_seconds == 0.75
    assert result.end_seconds == 2.25
    assert result.duration_seconds > 0.0


def test_slice_clip_invalid_intervals_raise(tmp_path: Path) -> None:
    src_video = tmp_path / "source.mp4"
    create_test_video(src_video, duration_seconds=2.0)

    out_clip = tmp_path / "bad.mp4"

    # end <= start
    with pytest.raises(ValueError):
        ClipSlicer.slice_clip(src_video, out_clip, start_seconds=2.0, end_seconds=1.0)

    # start < 0
    with pytest.raises(ValueError):
        ClipSlicer.slice_clip(src_video, out_clip, start_seconds=-1.0, end_seconds=1.0)


def test_slice_clip_missing_file_raises() -> None:
    with pytest.raises(FileNotFoundError):
        ClipSlicer.slice_clip("missing.mp4", "out.mp4", start_seconds=0.0, end_seconds=1.0)
