"""Decode uploaded compressed reference audio into a task-owned WAV file."""
import os
import shutil
import subprocess
from pathlib import Path


def prepare_reference_audio(source: Path, directory: Path) -> Path:
    if source.suffix.lower() == ".wav":
        return source
    ffmpeg = os.environ.get("SMARTCOURSE_FFMPEG") or shutil.which("ffmpeg")
    if not ffmpeg:
        raise ValueError("需要 FFmpeg 读取当前参考音频格式")
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / "speaker-normalized.wav"
    subprocess.run([ffmpeg, "-y", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", str(output)], check=True, capture_output=True, timeout=90)
    return output
