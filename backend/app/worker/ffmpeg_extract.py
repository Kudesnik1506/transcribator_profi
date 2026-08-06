import subprocess
from dataclasses import dataclass
from pathlib import Path


class FfmpegError(RuntimeError):
    pass


@dataclass
class AudioChunk:
    idx: int
    start_sec: float
    end_sec: float
    path: Path


def _run_checked(args: list[str]) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode != 0:
        raise FfmpegError(result.stderr)
    return result


def extract_audio(input_path: str | Path, output_path: str | Path) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path)

    _run_checked(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-sn",
            "-dn",
            "-map",
            "0:a:0",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-acodec",
            "libopus",
            "-b:a",
            "24k",
            str(output_path),
        ]
    )
    return output_path


def _probe_duration_sec(path: Path) -> float:
    result = _run_checked(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)]
    )
    return float(result.stdout.strip())


def split_audio_into_chunks(
    audio_path: str | Path, output_dir: str | Path, chunk_duration_sec: int = 900
) -> list[AudioChunk]:
    audio_path = Path(audio_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(output_dir / "chunk_%03d.ogg")

    _run_checked(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(audio_path),
            "-f",
            "segment",
            "-segment_time",
            str(chunk_duration_sec),
            "-c",
            "copy",
            "-reset_timestamps",
            "1",
            pattern,
        ]
    )

    chunks: list[AudioChunk] = []
    offset_sec = 0.0
    for idx, chunk_path in enumerate(sorted(output_dir.glob("chunk_*.ogg"))):
        duration = _probe_duration_sec(chunk_path)
        chunks.append(AudioChunk(idx=idx, start_sec=offset_sec, end_sec=offset_sec + duration, path=chunk_path))
        offset_sec += duration
    return chunks
