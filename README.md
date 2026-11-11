# VidClip

**Local-first video highlight finder and short-form clip studio.**

VidClip turns videos you already have permission to use into ranked, reviewable short clips. It is designed for modest Android hardware through Termux, while remaining usable on Linux, macOS, and Windows.

> **Current status:** Foundation release. The first engine provides offline media inspection, silence-aware candidate generation, scoring, and FFmpeg export. Transcript understanding, speaker tracking, trend research, and the graphical dashboard are planned modules—not features claimed to be complete today.

## Design principles

- **Works without AI:** core import, analysis, candidate ranking, and rendering do not require an API key, account, or internet connection.
- **AI is optional:** future providers plug into a common adapter. A failed or exhausted provider falls back to local analysis; VidClip never silently switches to a paid service.
- **Complete moments first:** target durations are configurable up to 120 seconds. A clip should end at a natural boundary, not be padded to an arbitrary length.
- **Small-device friendly:** Python standard library + FFmpeg/FFprobe for the base engine. Process one source at a time.
- **Review before publish:** exports are local. Publishing, account access, and outbound actions require explicit user approval.
- **Transparent scoring:** heuristic scores are estimates of editorial potential, not predictions or guarantees of views.

## Current capabilities

- Inspect a local video with FFprobe.
- Detect silence intervals with FFmpeg.
- Build candidate ranges from active-audio sections.
- Rank and de-overlap candidates.
- Export selected candidates as H.264 MP4.
- Save machine-readable JSON analysis reports.
- Preserve source files; generated files live in a separate output folder.

## Requirements

- Python 3.10+
- FFmpeg and FFprobe available on PATH

No Python third-party packages are required for the offline foundation.

### Termux / Android

Install Termux from a trusted source, then:

\`\`\`bash
pkg update && pkg upgrade -y
pkg install python ffmpeg git -y
git clone https://github.com/xxlm47/VidClip.git
cd VidClip
python -m vidclip --help
\`\`\`

To access Android shared storage, run \`termux-setup-storage\` and grant permission. Put source videos in \`~/storage/shared/Download\`, then pass the full file path to VidClip.

### Linux / macOS / Windows

Install Python 3.10+ and FFmpeg, clone this repository, and run the same Python commands.

## Quick start

Inspect a file:

\`\`\`bash
python -m vidclip inspect "/path/to/video.mp4"
\`\`\`

Find candidate moments (default maximum 5; maximum clip duration 120 seconds):

\`\`\`bash
python -m vidclip analyze "/path/to/video.mp4" --max-clips 5 --max-duration 120
\`\`\`

Render the top candidates:

\`\`\`bash
python -m vidclip clip "/path/to/video.mp4" --max-clips 5 --max-duration 120 --aspect vertical
\`\`\`

Use \`--aspect source\` to preserve the original frame. Vertical mode uses a centered 9:16 crop; intelligent subject tracking is planned separately.

## Output layout

Each run creates a project folder under \`output/\` containing:

- \`analysis.json\` — source metadata, settings, candidate timestamps, scores, and explanations.
- \`clips/\` — rendered MP4 files (for \`clip\` command).
- \`manifest.json\` — exported clip metadata (for \`clip\` command).

## How the first scoring pass works

The offline engine uses audio activity as a **candidate finder**, not as semantic understanding. It evaluates active-audio coverage, duration fit, and boundary padding. This can identify sections worth reviewing, but it cannot reliably know whether a joke lands, a story is complete, or a statement is misleading.

Planned transcript-aware scoring will add hook quality, standalone context, story completeness, useful information, emotional signals, and ending quality. Each signal will be reported separately so users can understand why a moment ranked highly.

## Roadmap

1. Offline candidate engine and repeatable tests.
2. Android-friendly import workflow and local browser dashboard.
3. Optional transcription adapters with provider health checks and hard no-billing rules.
4. Sentence-aware candidate boundaries and semantic ranking.
5. Caption generation, safe-area layouts, and subject-aware reframing.
6. Trend Radar and Content Scout with dated sources and niche filters.
7. Project history, feedback, and performance-informed ranking.
8. Optional integrations for user-approved publishing workflows.

## Rights and responsible use

Only process and publish videos you own or are authorized to use. Having a downloaded copy does not grant permission to republish it. VidClip does not bypass access controls, remove watermarks, or guarantee that content is free of third-party rights.

## License

MIT. See [LICENSE](LICENSE).
