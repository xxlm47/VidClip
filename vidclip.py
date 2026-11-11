#!/usr/bin/env python3
"""VidClip: lightweight, offline-first audio-activity video clipper.

This baseline detects active-audio windows, not semantic highlights.
Requires only Python's standard library plus ffmpeg/ffprobe.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class Candidate:
    start: float
    end: float
    active_seconds: float
    active_ratio: float
    score: float
    reasons: List[str]

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


def run(cmd: List[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, check=False, timeout=timeout)
    except FileNotFoundError as exc:
        raise RuntimeError("Required executable not found: " + cmd[0]) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Media analysis timed out. Try a shorter or lower-resolution source.") from exc


def require_tools() -> None:
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise RuntimeError("Missing required tool(s): " + ", ".join(missing) +
                           ". Install FFmpeg and ensure ffmpeg/ffprobe are on PATH.")


def probe(path: Path) -> dict:
    result = run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration,format_name:stream=codec_type,width,height,codec_name",
        "-of", "json", str(path)
    ], timeout=60)
    if result.returncode:
        raise RuntimeError("FFprobe could not read this file: " + result.stderr[-1200:])
    try:
        data = json.loads(result.stdout)
        duration = float(data["format"]["duration"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise RuntimeError("Could not determine the video's duration.")
    if not math.isfinite(duration) or duration <= 0:
        raise RuntimeError("Video duration is invalid.")
    streams = data.get("streams", [])
    if not any(s.get("codec_type") == "video" for s in streams):
        raise RuntimeError("The selected file has no video stream.")
    if not any(s.get("codec_type") == "audio" for s in streams):
        raise RuntimeError("This first version needs an audio stream to detect moments. Silent-video detection is planned.")
    return {"duration": duration, "format": data.get("format", {}).get("format_name"),
            "streams": streams}


def detect_silence(path: Path, noise_db: float, min_silence: float,
                   duration: float) -> List[Tuple[float, float]]:
    result = run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
        "-vn", "-af", "silencedetect=noise={}dB:d={}".format(noise_db, min_silence),
        "-f", "null", "-"
    ], timeout=max(180, int(duration * 2)))
    # FFmpeg writes filter diagnostics to stderr; a nonzero exit may indicate
    # a decode issue, so do not silently treat it as a successful analysis.
    if result.returncode:
        raise RuntimeError("FFmpeg audio analysis failed: " + result.stderr[-1600:])
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", result.stderr)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", result.stderr)]
    silences: List[Tuple[float, float]] = []
    for i, start in enumerate(starts):
        end = ends[i] if i < len(ends) else duration
        start = max(0.0, min(duration, start))
        end = max(start, min(duration, end))
        if end > start:
            silences.append((start, end))
    return silences


def active_regions(silences: List[Tuple[float, float]], duration: float) -> List[Tuple[float, float]]:
    regions: List[Tuple[float, float]] = []
    cursor = 0.0
    for start, end in sorted(silences):
        if start > cursor:
            regions.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        regions.append((cursor, duration))
    return [(a, b) for a, b in regions if b - a >= 0.35]


def overlap_seconds(start: float, end: float, regions: List[Tuple[float, float]]) -> float:
    return sum(max(0.0, min(end, b) - max(start, a)) for a, b in regions)


def make_candidates(regions: List[Tuple[float, float]], duration: float,
                    min_duration: float, max_duration: float) -> List[Candidate]:
    # Generate a small set of windows anchored at active regions. This avoids
    # scanning every second of a long file and keeps memory use negligible.
    candidates: List[Candidate] = []
    lengths = sorted(set([min_duration, min(30.0, max_duration),
                          min(45.0, max_duration), min(60.0, max_duration),
                          min(90.0, max_duration), max_duration]))
    for region_start, region_end in regions:
        for length in lengths:
            if length < min_duration or length <= 0:
                continue
            start = max(0.0, min(region_start - 0.8, duration - min_duration))
            end = min(duration, start + length)
            if end - start < min_duration:
                end = min(duration, start + min_duration)
            actual = end - start
            if actual < min_duration:
                continue
            active = overlap_seconds(start, end, regions)
            ratio = min(1.0, active / actual)
            if active < min(8.0, min_duration * 0.35):
                continue
            # Technical ranking only. Prefer meaningful active coverage, while
            # mildly preferring compact moments over padding long clips.
            compactness = 1.0 - 0.12 * ((actual - min_duration) /
                                        max(1.0, max_duration - min_duration))
            score = 100.0 * (0.78 * ratio + 0.22 * min(1.0, active / 35.0)) * compactness
            reasons = ["{:.0f}% active-audio coverage".format(ratio * 100),
                       "{:.1f}s active audio".format(active),
                       "silence-aware boundaries; semantic meaning not analyzed"]
            candidates.append(Candidate(start, end, active, ratio,
                                         round(max(0.0, min(100.0, score)), 1), reasons))
    # De-duplicate near-identical windows.
    unique = {}
    for c in candidates:
        key = (round(c.start), round(c.end))
        if key not in unique or c.score > unique[key].score:
            unique[key] = c
    return sorted(unique.values(), key=lambda c: c.score, reverse=True)


def choose_non_overlapping(candidates: List[Candidate], count: int,
                           overlap_limit: float = 0.20) -> List[Candidate]:
    chosen: List[Candidate] = []
    for candidate in candidates:
        if all(
            max(0.0, min(candidate.end, old.end) - max(candidate.start, old.start))
            / max(1.0, min(candidate.duration, old.duration)) <= overlap_limit
            for old in chosen
        ):
            chosen.append(candidate)
            if len(chosen) >= count:
                break
    return sorted(chosen, key=lambda c: c.start)


def export_clip(source: Path, candidate: Candidate, target: Path,
                aspect: str, index: int) -> None:
    start = max(0.0, candidate.start)
    duration = candidate.duration
    if aspect == "vertical":
        vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    else:
        # Preserve source aspect ratio; trim a possible odd edge pixel for yuv420p.
        vf = "scale=trunc(iw/2)*2:trunc(ih/2)*2"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", "{:.3f}".format(start), "-i", str(source),
        "-t", "{:.3f}".format(duration), "-map", "0:v:0", "-map", "0:a?",
        "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-b:a", "128k", "-movflags", "+faststart", str(target)
    ]
    result = run(cmd, timeout=max(300, int(duration * 8)))
    if result.returncode:
        raise RuntimeError("Export failed for clip {}: {}".format(index, result.stderr[-1200:]))


def analyze(args: argparse.Namespace) -> int:
    source = Path(args.input).expanduser().resolve()
    if not source.is_file():
        raise RuntimeError("Input file does not exist: " + str(source))
    if source.suffix.lower() in (".mp3", ".wav", ".m4a", ".aac", ".flac"):
        raise RuntimeError("Please select a video file, not an audio-only file.")
    require_tools()
    metadata = probe(source)
    duration = metadata["duration"]
    if args.max_duration > 120:
        raise RuntimeError("The maximum supported clip length is 120 seconds.")
    if args.min_duration < 8 or args.min_duration > args.max_duration:
        raise RuntimeError("Minimum duration must be at least 8 seconds and no greater than max duration.")
    print("VidClip | {}".format(source.name))
    print("Duration: {:.1f}s | analyzing audio activity...".format(duration))
    silences = detect_silence(source, args.noise_db, args.silence_duration, duration)
    regions = active_regions(silences, duration)
    if not regions:
        raise RuntimeError("No active-audio regions detected. Try a different --noise-db value.")
    candidates = make_candidates(regions, duration, args.min_duration, args.max_duration)
    selected = choose_non_overlapping(candidates, args.clips)
    if not selected:
        raise RuntimeError("No suitable candidates found. Try lowering --min-duration or adjusting --noise-db.")
    outdir = Path(args.output).expanduser() if args.output else (
        Path("output") / source.stem)
    outdir.mkdir(parents=True, exist_ok=True)
    report_items = []
    for index, item in enumerate(selected, 1):
        filename = "clip_{:02d}_{:05.1f}s.mp4".format(index, item.start).replace(".", "_")
        target = outdir / filename
        print("Exporting {}/{}: {:.1f}s–{:.1f}s | score {}".format(
            index, len(selected), item.start, item.end, item.score))
        export_clip(source, item, target, args.aspect, index)
        entry = asdict(item)
        entry.update({"clip": filename, "duration": round(item.duration, 2),
                      "score_type": "baseline_technical_not_viral"})
        report_items.append(entry)
    report = {
        "app": "VidClip",
        "version": "0.1.0-dev",
        "source": source.name,
        "source_duration_seconds": round(duration, 3),
        "analysis": "FFmpeg silence/activity detection; no transcription or semantic AI",
        "score_warning": "Scores estimate audio activity and compactness, not audience interest or virality.",
        "settings": {"noise_db": args.noise_db, "silence_duration": args.silence_duration,
                     "min_duration": args.min_duration, "max_duration": args.max_duration,
                     "aspect": args.aspect},
        "clips": report_items
    }
    (outdir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (outdir / "report.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "clip", "start", "end", "duration", "active_seconds",
            "active_ratio", "score", "score_type", "reasons"])
        writer.writeheader()
        for row in report_items:
            writer.writerow({k: json.dumps(row[k]) if k == "reasons" else row.get(k)
                             for k in writer.fieldnames})
    print("\\nDone. {} clips saved to {}".format(len(selected), outdir.resolve()))
    print("Review report.json before publishing. Scores are not predictions of views.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find and export audio-active moments from a video (offline baseline).")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("analyze", help="analyze a video and export ranked clips")
    p.add_argument("input", help="path to a local video file")
    p.add_argument("--clips", type=int, default=5, help="number of non-overlapping clips (default: 5)")
    p.add_argument("--min-duration", type=float, default=15.0, help="minimum clip length in seconds")
    p.add_argument("--max-duration", type=float, default=120.0, help="maximum clip length; hard limit 120 seconds")
    p.add_argument("--noise-db", type=float, default=-32.0, help="silence threshold in dB (default: -32)")
    p.add_argument("--silence-duration", type=float, default=0.45, help="minimum silence interval in seconds")
    p.add_argument("--aspect", choices=("source", "vertical"), default="source",
                   help="preserve source frame or center-crop to 9:16")
    p.add_argument("--output", help="output folder (default: output/<video-name>)")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.clips < 1 or args.clips > 50:
        parser.error("--clips must be between 1 and 50")
    try:
        return analyze(args)
    except (RuntimeError, OSError, ValueError) as exc:
        print("VidClip error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
