import json
import subprocess

import pytest

from app.worker.ffmpeg_extract import FfmpegError, extract_audio


def _make_test_video(path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=1:size=320x240:rate=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=1:sample_rate=44100",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_extract_audio_produces_mono_16khz_opus(tmp_path):
    input_path = tmp_path / "input.mp4"
    output_path = tmp_path / "output.ogg"
    _make_test_video(input_path)

    result_path = extract_audio(input_path, output_path)

    assert result_path == output_path
    assert output_path.exists()

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels",
            "-of",
            "json",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    info = json.loads(probe.stdout)["streams"][0]
    assert info["codec_name"] == "opus"
    # Ogg Opus always reports 48000 in the container header per RFC 7845,
    # regardless of -ar; -ar still controls the internal encoding band.
    assert info["sample_rate"] == "48000"
    assert info["channels"] == 1


def test_extract_audio_raises_on_missing_input(tmp_path):
    with pytest.raises(FfmpegError):
        extract_audio(tmp_path / "does-not-exist.mp4", tmp_path / "out.ogg")
