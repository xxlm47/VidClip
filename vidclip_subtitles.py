"""Optional local speech-to-subtitle helpers for VidClip.

Automatic transcription uses whisper.cpp only when the user supplies a local model.
No model download, network request, account, or paid API is performed.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Iterable


def _run(command, timeout=7200):
    try:
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, check=False, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError("Required executable not found: " + command[0]) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Subtitle generation timed out. Try a smaller Whisper model.") from exc
    if result.returncode:
        raise RuntimeError("Subtitle command failed: " + result.stderr[-1800:])
    return result


def transcribe_with_whisper(source: Path, workdir: Path, model: str,
                            executable: str = "whisper-cli") -> Path:
    """Create a timed SRT with a local whisper.cpp model."""
    if shutil.which(executable) is None:
        raise RuntimeError(
            "whisper.cpp was not found. Install/build whisper-cli, then pass --whisper-cli PATH."
        )
    model_path = Path(model).expanduser().resolve()
    if not model_path.is_file():
        raise RuntimeError("Whisper model file does not exist: " + str(model_path))
    workdir.mkdir(parents=True, exist_ok=True)
    audio = workdir / "vidclip_audio_16k_mono.wav"
    output_base = workdir / "vidclip_transcript"
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(audio)
    ], timeout=1800)
    _run([executable, "-m", str(model_path), "-f", str(audio), "-osrt",
          "-of", str(output_base)], timeout=7200)
    subtitle_file = output_base.with_suffix(".srt")
    if not subtitle_file.is_file() or subtitle_file.stat().st_size == 0:
        raise RuntimeError("whisper.cpp completed but did not create a non-empty SRT file.")
    return subtitle_file


def _stamp(seconds: float) -> str:
    milliseconds = max(0, int(round(seconds * 1000)))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, millis = divmod(remainder, 1000)
    return "{:02d}:{:02d}:{:02d},{:03d}".format(hours, minutes, whole_seconds, millis)


def write_clip_srt(target: Path, cues: Iterable, clip_start: float, clip_end: float) -> int:
    """Write only overlapping cues and rebase timestamps to the clip start."""
    rows = []
    for cue in cues:
        start = max(float(cue.start), clip_start)
        end = min(float(cue.end), clip_end)
        if end <= start:
            continue
        rows.append((start - clip_start, end - clip_start, cue.text))
    rows.sort(key=lambda row: (row[0], row[1]))
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        for index, (start, end, text) in enumerate(rows, 1):
            handle.write("{}\n{} --> {}\n{}\n\n".format(
                index, _stamp(start), _stamp(end), text.strip()))
    return len(rows)


def burn_subtitles_filter(path: Path) -> str:
    """Return an FFmpeg subtitles filter with a safely escaped local path."""
    value = str(path.resolve()).replace("\\", "\\\\")
    for char in (":", "'", ",", "[", "]"):
        value = value.replace(char, "\\" + char)
    return "subtitles=filename='{}'".format(value)

def extract_embedded_subtitles(source: Path, workdir: Path):
    """Extract the first text-based embedded subtitle stream to SRT, if present."""
    probe = _run([
        "ffprobe", "-v", "error", "-select_streams", "s",
        "-show_entries", "stream=index,codec_name", "-of", "json", str(source)
    ], timeout=60)
    import json
    try:
        streams = json.loads(probe.stdout).get("streams", [])
    except (ValueError, TypeError):
        streams = []
    image_codecs = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}
    workdir.mkdir(parents=True, exist_ok=True)
    for stream in streams:
        if stream.get("codec_name") in image_codecs:
            continue
        index = stream.get("index")
        if index is None:
            continue
        target = workdir / "vidclip_embedded_subtitles.srt"
        try:
            _run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source),
                "-map", "0:{}".format(index), "-c:s", "srt", str(target)
            ], timeout=300)
        except RuntimeError:
            continue
        if target.is_file() and target.stat().st_size:
            return target
    return None
