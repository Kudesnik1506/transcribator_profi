import subprocess

import pytest

from app.worker.ffmpeg_extract import split_audio_into_chunks


def _make_test_audio(path, duration_sec: int) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration_sec}:sample_rate=48000",
            "-c:a",
            "libopus",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_split_audio_into_chunks_splits_by_duration(tmp_path):
    audio_path = tmp_path / "audio.ogg"
    _make_test_audio(audio_path, duration_sec=5)
    output_dir = tmp_path / "chunks"

    chunks = split_audio_into_chunks(audio_path, output_dir, chunk_duration_sec=2)

    assert len(chunks) == 3
    assert [c.idx for c in chunks] == [0, 1, 2]
    assert chunks[0].start_sec == pytest.approx(0.0, abs=0.05)
    assert chunks[0].end_sec == pytest.approx(2.0, abs=0.2)
    assert chunks[1].start_sec == pytest.approx(chunks[0].end_sec, abs=0.001)
    assert chunks[2].start_sec == pytest.approx(chunks[1].end_sec, abs=0.001)
    assert chunks[-1].end_sec == pytest.approx(5.0, abs=0.3)
    for chunk in chunks:
        assert chunk.path.exists()


def test_split_audio_into_chunks_single_chunk_when_shorter_than_duration(tmp_path):
    audio_path = tmp_path / "audio.ogg"
    _make_test_audio(audio_path, duration_sec=1)
    output_dir = tmp_path / "chunks"

    chunks = split_audio_into_chunks(audio_path, output_dir, chunk_duration_sec=900)

    assert len(chunks) == 1
    assert chunks[0].start_sec == 0.0
    assert chunks[0].end_sec == pytest.approx(1.0, abs=0.1)
