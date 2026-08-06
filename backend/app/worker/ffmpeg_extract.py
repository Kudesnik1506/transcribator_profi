import subprocess
from pathlib import Path


class FfmpegError(RuntimeError):
    pass


def extract_audio(input_path: str | Path, output_path: str | Path) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path)

    result = subprocess.run(
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
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FfmpegError(result.stderr)
    return output_path
