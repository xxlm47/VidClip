"""Small, dependency-free FFmpeg analysis engine for VidClip."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


class VidClipError(RuntimeError):
    """Raised for expected media or tool errors."""


@dataclass
class MediaInfo:
    path: str
    duration: float
    width: int | None
    height: int | None
    fps: float | None
    has_audio: bool
    video_codec: str | None
    audio_codec: str | None


@dataclass
class Candidate:
    start: float
    end: float
    duration: float
    score: float
    active_ratio: float
    explanation: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


def require_tools() -> tuple[str, str]:
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise VidClipError("FFmpeg and FFprobe must both be installed and available on PATH.")
    return ffmpeg, ffprobe


def _run(args: list[str], timeout: int = 180) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise VidClipError(f"Media command timed out after {timeout} seconds.") from exc


def inspect_media(path: str | Path) -> MediaInfo:
    _, ffprobe = require_tools()
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise VidClipError(f"Video file not found: {source}")
    result = _run([
        ffprobe, "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate",
        "-of", "json", str(source),
    ])
    if result.returncode != 0:
        raise VidClipError(result.stderr.strip() or "FFprobe could not read this file.")
    try:
        payload = json.loads(result.stdout)
        duration = float(payload.get("format", {}).get("duration") or 0)
        streams = payload.get("streams", [])
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise VidClipError("FFprobe returned invalid media metadata.") from exc
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    if duration <= 0 or not video:
        raise VidClipError("The input must contain a readable video stream with a valid duration.")
    fps = None
    try:
        numerator, denominator = video.get("avg_frame_rate", "0/0").split("/", 1)
        if float(denominator):
            fps = float(numerator) / float(denominator)
    except (ValueError, ZeroDivisionError):
        pass
    return MediaInfo(
        path=str(source), duration=duration,
        width=int(video["width"]) if video.get("width") else None,
        height=int(video["height"]) if video.get("height") else None,
        fps=fps, has_audio=audio is not None,
        video_codec=video.get("codec_name"),
        audio_codec=audio.get("codec_name") if audio else None,
    )


def detect_silences(path: str | Path, noise_db: float = -35.0,
                    min_silence: float = 0.45,
                    media_duration: float | None = None) -> list[tuple[float, float]]:
    """Return silence intervals using FFmpeg's silencedetect filter."""
    ffmpeg, _ = require_tools()
    source = Path(path).expanduser().resolve()
    result = _run([
        ffmpeg, "-hide_banner", "-nostats", "-i", str(source),
        "-vn", "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
        "-f", "null", "-",
    ], timeout=900)
    log = result.stderr
    if result.returncode != 0:
        raise VidClipError(log.strip()[-1200:] or "Audio analysis failed.")
    starts: list[float] = []
    intervals: list[tuple[float, float]] = []
    for line in log.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        end_match = re.search(r"silence_end:\s*([0-9.]+)", line)
        if start_match:
            starts.append(float(start_match.group(1)))
        if end_match:
            end = float(end_match.group(1))
            start = starts.pop(0) if starts else 0.0
            if end > start:
                intervals.append((start, end))
    # FFmpeg emits silence_start without silence_end when silence continues to EOF.
    if starts and media_duration is not None:
        start = starts[0]
        if media_duration > start:
            intervals.append((start, media_duration))
    return intervals


def active_regions(duration: float, silences: Iterable[tuple[float, float]],
                   merge_gap: float = 2.0) -> list[tuple[float, float]]:
    """Invert silence intervals and merge nearby active regions."""
    cursor, active = 0.0, []
    for start, end in sorted(silences):
        start = max(0.0, min(duration, start))
        end = max(start, min(duration, end))
        if start > cursor:
            active.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        active.append((cursor, duration))
    merged: list[list[float]] = []
    for start, end in active:
        if end - start <= 0.05:
            continue
        if merged and start - merged[-1][1] <= merge_gap:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return [(a, b) for a, b in merged]


def _overlap(a: Candidate, b: Candidate) -> bool:
    return a.start < b.end and b.start < a.end


def find_candidates(duration: float, silences: Iterable[tuple[float, float]],
                    min_duration: float = 15.0, max_duration: float = 120.0,
                    max_clips: int = 5, merge_gap: float = 2.0) -> list[Candidate]:
    """Build ranked windows from active regions; scores are provisional heuristics."""
    if min_duration <= 0 or max_duration < min_duration or max_duration > 120:
        raise VidClipError("Duration limits must satisfy 0 < min <= max <= 120 seconds.")
    if max_clips < 1:
        raise VidClipError("max_clips must be at least 1.")

    regions = active_regions(duration, silences, merge_gap)
    candidates: list[Candidate] = []
    windows: list[tuple[float, float]] = []

    for index, (start, end) in enumerate(regions):
        region_length = end - start
        if region_length >= min_duration:
            if region_length <= max_duration:
                windows.append((start, end))
            else:
                # Long uninterrupted speech still needs useful clip windows.
                stride = max(min_duration, max_duration * 0.75)
                cursor = start
                while cursor + min_duration <= end:
                    clip_end = min(end, cursor + max_duration)
                    if clip_end - cursor >= min_duration:
                        windows.append((cursor, clip_end))
                    cursor += stride
                final_start = max(start, end - max_duration)
                if final_start + min_duration <= end:
                    windows.append((final_start, end))

        # Also join adjacent active sections across short pauses, without exceeding max.
        joined_end = end
        for next_start, next_end in regions[index + 1:]:
            if next_start - joined_end > merge_gap:
                break
            if next_end - start > max_duration:
                break
            joined_end = next_end
            if joined_end - start >= min_duration:
                windows.append((start, joined_end))

    # Score against the unmerged audio-active intervals. The segmentation pass
    # merges short pauses to preserve sentences, but those pauses must not count
    # as active audio when measuring a candidate.
    raw_active: list[tuple[float, float]] = []
    cursor = 0.0
    for silence_start, silence_end in sorted(silences):
        silence_start = max(0.0, min(duration, silence_start))
        silence_end = max(silence_start, min(duration, silence_end))
        if silence_start > cursor:
            raw_active.append((cursor, silence_start))
        cursor = max(cursor, silence_end)
    if cursor < duration:
        raw_active.append((cursor, duration))

    seen: set[tuple[float, float]] = set()
    for start, end in windows:
        key = (round(start, 3), round(end, 3))
        if key in seen:
            continue
        seen.add(key)
        length = end - start
        covered = sum(max(0.0, min(end, b) - max(start, a))
                      for a, b in raw_active)
        ratio = min(1.0, covered / max(length, 0.001))
        target = min(max_duration, 60.0)
        duration_fit = max(0.0, 1.0 - abs(length - target) / max(max_duration, 60.0))
        score = round(max(0.0, min(100.0, 65 * ratio + 35 * duration_fit)), 1)
        candidates.append(Candidate(
            round(start, 3), round(end, 3), round(length, 3), score,
            round(ratio, 3), [
                f"{ratio:.0%} estimated audio-active coverage (silence threshold based)",
                f"Duration-fit component: {duration_fit:.0%}",
                "Provisional heuristic only; no transcript, story, or highlight understanding",
            ],
        ))

    candidates.sort(key=lambda c: (c.score, c.active_ratio, c.duration), reverse=True)
    selected: list[Candidate] = []
    for candidate in candidates:
        if any(_overlap(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
        if len(selected) >= max_clips:
            break
    return sorted(selected, key=lambda c: c.start)

def analyze(path: str | Path, min_duration: float = 15.0,
            max_duration: float = 120.0, max_clips: int = 5,
            noise_db: float = -35.0, min_silence: float = 0.45) -> dict:
    info = inspect_media(path)
    if not info.has_audio:
        raise VidClipError("This first engine requires an audio stream. Video-only analysis is planned.")
    silences = detect_silences(path, noise_db, min_silence, info.duration)
    candidates = find_candidates(info.duration, silences, min_duration, max_duration, max_clips)
    return {
        "engine": "vidclip-offline-audio-v1",
        "score_type": "provisional_heuristic",
        "media": asdict(info),
        "settings": {"min_duration": min_duration, "max_duration": max_duration,
                     "max_clips": max_clips, "noise_db": noise_db,
                     "min_silence": min_silence},
        "silences": [{"start": round(a, 3), "end": round(b, 3)} for a, b in silences],
        "candidates": [c.to_dict() for c in candidates],
        "limitations": [
            "Audio activity is not semantic understanding.",
            "The score measures silence-threshold activity and duration fit; it does not identify viral moments.",
            "The engine cannot yet verify story completeness, punchlines, context, or factual accuracy.",
            "Review candidates before publishing.",
        ],
    }


def render_clip(source: str | Path, candidate: Candidate, destination: str | Path,
                aspect: str = "vertical", crf: int = 23) -> None:
    ffmpeg, _ = require_tools()
    src, out = Path(source).expanduser().resolve(), Path(destination).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    args = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-ss", f"{candidate.start:.3f}", "-i", str(src),
            "-t", f"{candidate.duration:.3f}", "-map", "0:v:0", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"]
    if aspect == "vertical":
        args += ["-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"]
    elif aspect != "source":
        raise VidClipError("Aspect must be 'vertical' or 'source'.")
    args.append(str(out))
    result = _run(args, timeout=1800)
    if result.returncode != 0:
        raise VidClipError(result.stderr.strip()[-1600:] or "FFmpeg export failed.")
