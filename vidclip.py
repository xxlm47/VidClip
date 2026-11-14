#!/usr/bin/env python3
"""VidClip: lightweight, offline-first audio-activity video clipper.

This baseline detects active-audio windows, not semantic highlights.
Requires only Python's standard library plus ffmpeg/ffprobe.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
import math
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional, Tuple
import tempfile

try:
    from vidclip_story import attach_transcript_scores, parse_subtitles
    from vidclip_subtitles import transcribe_with_whisper, write_clip_srt, burn_subtitles_filter, extract_embedded_subtitles
except ImportError:
    attach_transcript_scores = None
    parse_subtitles = None
    transcribe_with_whisper = write_clip_srt = burn_subtitles_filter = extract_embedded_subtitles = None

try:
    from vidclip_metadata import build_clip_metadata, write_metadata_files
except ImportError:
    build_clip_metadata = write_metadata_files = None


@dataclass
class Candidate:
    start: float
    end: float
    active_seconds: float
    active_ratio: float
    score: float
    reasons: List[str]
    story_score: float = 0.0
    story_analysis: Optional[dict] = None

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
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    return {"duration": duration, "format": data.get("format", {}).get("format_name"),
            "streams": streams, "has_audio": has_audio}


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
                    min_duration: float, max_duration: float,
                    allow_silent: bool = False) -> List[Candidate]:
    # Generate a small set of windows anchored at active regions. This avoids
    # scanning every second of a long file and keeps memory use negligible.
    candidates: List[Candidate] = []
    lengths = sorted(set([min_duration, min(30.0, max_duration),
                          min(45.0, max_duration), min(60.0, max_duration),
                          min(90.0, max_duration), max_duration]))
    # Slide across the entire source. Anchoring only at the first active region
    # would otherwise return several clips from the opening minutes of a long video.
    stride = max(8.0, min_duration / 2.0)
    steps = int(math.ceil(duration / stride))
    for step in range(steps):
        start = step * stride
        if start >= duration:
            continue
        for length in lengths:
            if length < min_duration or length <= 0:
                continue
            end = min(duration, start + length)
            actual = end - start
            if actual < min_duration:
                continue
            active = overlap_seconds(start, end, regions)
            ratio = min(1.0, active / actual)
            if active < min(8.0, min_duration * 0.35) and not allow_silent:
                continue
            # Video-only candidates are deliberately unscored: do not invent an audio score.
            if allow_silent and active <= 0.0:
                candidates.append(Candidate(start, end, 0.0, 0.0, 0.0,
                    ["no audio stream; video-only candidate requires manual review"]))
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
                           video_duration: float,
                           overlap_limit: float = 0.20) -> List[Candidate]:
    chosen: List[Candidate] = []
    # Encourage coverage across the source instead of returning five adjacent
    # windows from the beginning when many candidates have similar scores.
    min_midpoint_gap = max(0.0, video_duration / max(1, count) * 0.75)
    ordered = sorted(candidates, key=lambda c: (
        -(0.55 * c.score + 0.45 * c.story_score) if c.story_score > 0 else -c.score,
        c.start))
    for candidate in ordered:
        midpoint = (candidate.start + candidate.end) / 2.0
        separated = all(
            abs(midpoint - ((old.start + old.end) / 2.0)) >= min_midpoint_gap
            for old in chosen
        )
        no_heavy_overlap = all(
            max(0.0, min(candidate.end, old.end) - max(candidate.start, old.start))
            / max(1.0, min(candidate.duration, old.duration)) <= overlap_limit
            for old in chosen
        )
        if separated and no_heavy_overlap:
            chosen.append(candidate)
            if len(chosen) >= count:
                break
    # If temporal spreading was too strict, fill remaining slots with the
    # highest-scoring non-overlapping candidates.
    if len(chosen) < count:
        for candidate in ordered:
            if candidate in chosen:
                continue
            no_heavy_overlap = all(
                max(0.0, min(candidate.end, old.end) - max(candidate.start, old.start))
                / max(1.0, min(candidate.duration, old.duration)) <= overlap_limit
                for old in chosen
            )
            if no_heavy_overlap:
                chosen.append(candidate)
                if len(chosen) >= count:
                    break
    return sorted(chosen, key=lambda c: c.start)


def make_clip_filename(index: int, start: float) -> str:
    """Return a safe MP4 filename while preserving the real file extension."""
    start_label = "{:05.1f}".format(start).replace(".", "_")
    return "clip_{:02d}_{}s.mp4".format(index, start_label)


def export_clip(source: Path, candidate: Candidate, target: Path,
                aspect: str, index: int, subtitle_path: Optional[Path] = None) -> None:
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
        "-vf", (vf + "," + burn_subtitles_filter(subtitle_path) if subtitle_path else vf), "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac",
        "-b:a", "128k", "-movflags", "+faststart", str(target)
    ]
    result = run(cmd, timeout=max(300, int(duration * 8)))
    if result.returncode:
        raise RuntimeError("Export failed for clip {}: {}".format(index, result.stderr[-1200:]))


def validate_export(path: Path, expected_duration: float, has_audio: bool,
                    minimum_duration: float = 8.0) -> dict:
    """Verify the exported file can be probed and contains expected streams."""
    result = run([
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration:stream=codec_type,width,height",
        "-of", "json", str(path)
    ], timeout=60)
    if result.returncode:
        raise RuntimeError("Export QA failed for {}: {}".format(path.name, result.stderr[-1000:]))
    try:
        data = json.loads(result.stdout)
        actual_duration = float(data["format"]["duration"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise RuntimeError("Export QA could not read duration for " + path.name)
    streams = data.get("streams", [])
    has_video = any(item.get("codec_type") == "video" for item in streams)
    exported_audio = any(item.get("codec_type") == "audio" for item in streams)
    if not has_video or (has_audio and not exported_audio):
        raise RuntimeError("Export QA found a missing required stream in " + path.name)
    if actual_duration < minimum_duration - 1.5:
        raise RuntimeError("Export QA rejected {}: {:.1f}s is shorter than the required {:.1f}s minimum.".format(
            path.name, actual_duration, minimum_duration))
    if actual_duration <= 0 or actual_duration > expected_duration + 1.5:
        raise RuntimeError("Export QA found an invalid duration in " + path.name)
    video = next(item for item in streams if item.get("codec_type") == "video")
    return {"valid": True, "duration_seconds": round(actual_duration, 3),
            "has_video": has_video, "has_audio": exported_audio,
            "width": video.get("width"), "height": video.get("height")}


def analyze(args: argparse.Namespace) -> int:
    source = Path(args.input).expanduser().resolve()
    if not source.is_file():
        raise RuntimeError("Input file does not exist: " + str(source))
    if source.suffix.lower() in (".mp3", ".wav", ".m4a", ".aac", ".flac"):
        raise RuntimeError("Please select a video file, not an audio-only file.")
    require_tools()
    metadata = probe(source)
    duration = metadata["duration"]
    if not math.isfinite(args.min_duration) or not math.isfinite(args.max_duration):
        raise RuntimeError("Clip duration settings must be finite numbers.")
    if args.max_duration < 8 or args.max_duration > 120:
        raise RuntimeError("Maximum duration must be between 8 and 120 seconds.")
    if args.min_duration < 8 or args.min_duration > args.max_duration:
        raise RuntimeError("Minimum duration must be at least 8 seconds and no greater than max duration.")
    if not math.isfinite(args.noise_db) or not -90 <= args.noise_db <= 0:
        raise RuntimeError("--noise-db must be between -90 and 0 dB.")
    if not math.isfinite(args.silence_duration) or args.silence_duration <= 0:
        raise RuntimeError("--silence-duration must be greater than zero.")
    print("VidClip | {}".format(source.name))
    print("Clip target: {} clips | {:.0f}–{:.0f} seconds each | subtitles: {}".format(
        args.clips, args.min_duration, args.max_duration, args.subtitle_mode))
    has_audio = metadata["has_audio"]
    if has_audio:
        print("Duration: {:.1f}s | analyzing audio activity...".format(duration))
        silences = detect_silence(source, args.noise_db, args.silence_duration, duration)
        regions = active_regions(silences, duration)
        if not regions:
            raise RuntimeError("No active-audio regions detected. Try a different --noise-db value.")
    else:
        print("Duration: {:.1f}s | no audio stream; creating unscored video-only candidates.".format(duration))
        regions = []
    candidates = make_candidates(regions, duration, args.min_duration, args.max_duration,
                                 allow_silent=not has_audio)
    transcript_path = getattr(args, "transcript", None)
    transcript_cues = []
    generated_transcript = False
    embedded_transcript = False
    temp_transcript_dir = None
    # A transcript can power metadata even when subtitle files are disabled.
    # Subtitle export remains disabled unless --subtitle-mode requests it.
    if getattr(args, "subtitle_mode", "none") == "none" and not transcript_path:
        transcript_path = None
    elif not transcript_path:
        if extract_embedded_subtitles is None:
            raise RuntimeError("Subtitle helper unavailable; restore vidclip_subtitles.py.")
        temp_transcript_dir = tempfile.TemporaryDirectory(prefix="vidclip-subtitles-")
        transcript_path = extract_embedded_subtitles(source, Path(temp_transcript_dir.name))
        if transcript_path:
            embedded_transcript = True
            print("Subtitles: extracted an embedded text subtitle track.")
    if not transcript_path and getattr(args, "whisper_model", None):
        if transcribe_with_whisper is None:
            raise RuntimeError("Subtitle helper unavailable; restore vidclip_subtitles.py.")
        if temp_transcript_dir is None:
            temp_transcript_dir = tempfile.TemporaryDirectory(prefix="vidclip-subtitles-")
        transcript_path = transcribe_with_whisper(source, Path(temp_transcript_dir.name),
                                                   args.whisper_model, args.whisper_cli)
        generated_transcript = True
        print("Automatic subtitles: generated locally with whisper.cpp.")
    if transcript_path:
        if parse_subtitles is None or attach_transcript_scores is None:
            raise RuntimeError("Transcript helper is unavailable; restore vidclip_story.py.")
        transcript_cues = parse_subtitles(transcript_path)
        attach_transcript_scores(candidates, transcript_cues)
        print("Transcript: {} timed cues loaded; ranking includes lexical evidence.".format(len(transcript_cues)))
    if duration + 0.01 < args.clips * args.min_duration:
        raise RuntimeError("Source is too short for {} non-overlapping clips of at least {:.0f}s (needs at least {:.0f}s; source is {:.1f}s).".format(args.clips, args.min_duration, args.clips * args.min_duration, duration))
    selected = choose_non_overlapping(candidates, args.clips, duration)
    if len(selected) != args.clips:
        raise RuntimeError("Could only find {} of {} requested clips meeting the minimum duration. Try a longer source or adjust --noise-db; VidClip will not export short filler clips.".format(len(selected), args.clips))
    too_short = [item for item in selected if item.duration + 0.01 < args.min_duration]
    if too_short:
        raise RuntimeError("Internal selection safety check stopped export: a selected clip was shorter than {:.1f}s.".format(
            args.min_duration))
    if args.output:
        outdir = Path(args.output).expanduser()
        if outdir.exists() and any(outdir.iterdir()):
            raise RuntimeError("The selected output folder is not empty; choose a new folder to protect existing exports.")
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        outdir = Path("output") / source.stem / run_id
    outdir.mkdir(parents=True, exist_ok=True)
    report_items = []
    metadata_items = []
    for index, item in enumerate(selected, 1):
        filename = make_clip_filename(index, item.start)
        target = outdir / filename
        print("Exporting {}/{}: {:.1f}s–{:.1f}s | score {}".format(
            index, len(selected), item.start, item.end, item.score))
        clip_subtitle = None
        if transcript_cues and getattr(args, "subtitle_mode", "burn") != "none":
            clip_subtitle = outdir / (target.stem + ".srt")
            write_clip_srt(clip_subtitle, transcript_cues, item.start, item.end)
            if getattr(args, "subtitle_mode", "sidecar") == "burn":
                export_subtitle_path = clip_subtitle
            else:
                export_subtitle_path = None
        else:
            export_subtitle_path = None
        export_clip(source, item, target, args.aspect, index, export_subtitle_path)
        qa = validate_export(target, item.duration, any(
            stream.get("codec_type") == "audio" for stream in metadata["streams"]),
            minimum_duration=args.min_duration)
        entry = asdict(item)
        entry["export_qa"] = qa
        entry.update({"clip": filename, "duration": round(item.duration, 2),
                      "score_type": "baseline_technical_not_viral"})
        if build_clip_metadata is not None:
            clip_meta = build_clip_metadata(transcript_cues, item.start, item.end, source.stem, index)
            clip_meta["clip"] = filename
            metadata_items.append(clip_meta)
            entry["social_metadata"] = clip_meta
        report_items.append(entry)
    report = {
        "app": "VidClip",
        "version": "0.1.0-dev",
        "source": source.name,
        "source_duration_seconds": round(duration, 3),
        "source_has_audio": has_audio,
        "analysis": ("video-only candidate windows (no audio stream)" if not has_audio else
                     "FFmpeg silence/activity plus optional timed-subtitle lexical heuristics"
                     if transcript_cues else "FFmpeg silence/activity detection; no transcription or semantic AI"),
        "score_warning": ("Technical scores estimate audio activity and compactness; transcript scores are lexical heuristics. "
                          "Video-only candidates receive zero audio score and require manual review. "
                          "No score predicts audience interest or virality."),
        "transcript": {"provided": bool(transcript_cues), "extracted_from_source": embedded_transcript, "generated_locally": generated_transcript,
                       "path": str(transcript_path) if transcript_cues else None,
                       "cue_count": len(transcript_cues),
                       "subtitle_mode": getattr(args, "subtitle_mode", "sidecar")},
        "review_required": True,
        "settings": {"noise_db": args.noise_db, "silence_duration": args.silence_duration,
                     "min_duration": args.min_duration, "max_duration": args.max_duration,
                     "aspect": args.aspect},
        "clips": report_items
    }
    (outdir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    if write_metadata_files is not None:
        write_metadata_files(outdir, metadata_items)
    with (outdir / "report.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "clip", "start", "end", "duration", "active_seconds",
            "active_ratio", "score", "story_score", "score_type", "reasons", "story_analysis", "export_qa"])
        writer.writeheader()
        for row in report_items:
            writer.writerow({k: json.dumps(row.get(k)) if k in ("reasons", "story_analysis", "export_qa") else row.get(k)
                             for k in writer.fieldnames})
    print("\nDone. {} clips saved to {}".format(len(selected), outdir.resolve()))
    # Mirror finished exports into Android shared storage when permission exists.
    android_shared = Path.home() / "storage" / "shared"
    android_root = android_shared / "Movies" / "VidClip"
    try:
        if android_shared.exists():
            android_out = android_root / source.stem / outdir.name
            android_out.mkdir(parents=True, exist_ok=True)
            for exported in outdir.iterdir():
                if exported.is_file():
                    shutil.copy2(str(exported), str(android_out / exported.name))
            print("Android copy: {}".format(android_out))
        else:
            print("Android copy skipped: run termux-setup-storage and allow storage access, then rerun VidClip.")
    except OSError as exc:
        print("Android copy failed: {}. Original exports remain at {}.".format(exc, outdir.resolve()))
    print("Review report.json before publishing. Scores are not predictions of views.")
    if temp_transcript_dir is not None:
        temp_transcript_dir.cleanup()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find and export video moments offline; audio signals improve ranking when available.")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("analyze", help="analyze a video and export ranked clips")
    p.add_argument("input", help="path to a local video file")
    p.add_argument("--clips", type=int, default=4, help="number of non-overlapping clips (default: 4)")
    p.add_argument("--min-duration", type=float, default=90.0, help="minimum clip length in seconds (default: 90)")
    p.add_argument("--max-duration", type=float, default=120.0, help="maximum clip length; hard limit 120 seconds")
    p.add_argument("--noise-db", type=float, default=-32.0, help="silence threshold in dB (default: -32)")
    p.add_argument("--silence-duration", type=float, default=0.45, help="minimum silence interval in seconds")
    p.add_argument("--aspect", choices=("source", "vertical"), default="source",
                   help="preserve source frame or center-crop to 9:16")
    p.add_argument("--transcript", help="optional timed .srt/.vtt sidecar; takes priority over auto transcription")
    p.add_argument("--whisper-model", help="local whisper.cpp GGML/GGUF model; enables offline auto-transcription when no sidecar is supplied")
    p.add_argument("--whisper-cli", default="whisper-cli", help="whisper.cpp executable (default: whisper-cli)")
    p.add_argument("--subtitle-mode", choices=("none", "sidecar", "burn"), default="none", help="disable subtitles (default), write editable SRT sidecars, or burn captions into each video")
    p.add_argument("--output", help="empty output folder (default: unique timestamped folder under output/<video-name>)")
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
