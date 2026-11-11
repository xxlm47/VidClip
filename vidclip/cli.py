"""Command-line interface for VidClip."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .core import Candidate, VidClipError, analyze, inspect_media, render_clip


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vidclip",
        description="Offline-first highlight detection and video clipping.")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("inspect", help="Read video metadata.")
    inspect.add_argument("video")
    for name, description in (
        ("analyze", "Find and rank candidate moments without exporting."),
        ("clip", "Analyze a video and export the top candidate clips."),
    ):
        cmd = sub.add_parser(name, help=description)
        cmd.add_argument("video")
        cmd.add_argument("--min-duration", type=float, default=15.0)
        cmd.add_argument("--max-duration", type=float, default=120.0)
        cmd.add_argument("--max-clips", type=int, default=5)
        cmd.add_argument("--noise-db", type=float, default=-35.0)
        cmd.add_argument("--min-silence", type=float, default=0.45)
        if name == "clip":
            cmd.add_argument("--aspect", choices=("vertical", "source"), default="vertical")
            cmd.add_argument("--crf", type=int, default=23)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            print(json.dumps(inspect_media(args.video).__dict__, indent=2))
            return 0

        report = analyze(args.video, args.min_duration, args.max_duration,
                         args.max_clips, args.noise_db, args.min_silence)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        project = Path("output") / f"{Path(args.video).stem}-{args.command}-{stamp}"
        project.mkdir(parents=True, exist_ok=True)
        report["project_dir"] = str(project)
        report_path = project / "analysis.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"Analysis saved: {report_path}")
        if not report["candidates"]:
            print("No candidate moments met the selected duration range.")
            print("Try lowering --min-duration or adjusting --noise-db.")
            return 0

        for number, item in enumerate(report["candidates"], 1):
            print(f"{number}. {item['start']:.1f}s–{item['end']:.1f}s "
                  f"({item['duration']:.1f}s) | provisional score {item['score']}/100")

        if args.command == "clip":
            clips_dir = project / "clips"
            manifest = []
            for number, item in enumerate(report["candidates"], 1):
                candidate = Candidate(**item)
                output = clips_dir / f"clip-{number:02d}-{candidate.start:.1f}s.mp4"
                render_clip(args.video, candidate, output, args.aspect, args.crf)
                manifest.append({"file": str(output), "start": candidate.start,
                    "end": candidate.end, "duration": candidate.duration,
                    "score": candidate.score, "aspect": args.aspect})
                print(f"Exported: {output}")
            (project / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return 0
    except VidClipError as exc:
        print(f"VidClip error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
