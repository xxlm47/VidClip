# VidClip

**Offline-first video highlight finder and clip exporter, designed for Android.**

VidClip turns a long video you have permission to use into a shortlist of shorter moments. The first release is deliberately lightweight: Python standard library + FFmpeg/FFprobe. No AI account, paid API, database server, or local model is required.

> **Status: early MVP (0.1.0-dev).** The baseline detector uses audio activity and silence boundaries. It does not understand speech meaning, detect jokes, verify story completeness, or predict views. Scores are technical ranking signals, not viral predictions.

## Why VidClip

- Android + Termux, including low-memory devices.
- Offline fallback with no AI quota or billing dependency.
- Transparent scoring: explain why a segment ranked highly and what the detector cannot know.
- Clips up to **120 seconds**; shorter clips are preferred when they contain a complete moment.
- Local files stay local. No upload, telemetry, or account required by the core.
- Optional transcription and semantic ranking can be added as separate providers later.

## MVP features

- Probe video metadata with FFprobe.
- Detect active-audio regions and silence boundaries with FFmpeg.
- Generate candidate windows up to 120 seconds.
- Rank candidates using speech/activity density and duration.
- Select configurable non-overlapping clips.
- Export MP4 (H.264 + AAC) in source aspect ratio or center-cropped 9:16.
- Save JSON and CSV reports with timestamps, scores, and detector limitations.
- Keep the original video unchanged.

## Requirements

- Python 3.9+ (standard library only)
- FFmpeg and FFprobe on PATH
- Termux storage permission if importing from shared Android storage

## Android / Termux quick start

```bash
pkg update -y
pkg install -y python ffmpeg git
termux-setup-storage
git clone https://github.com/xxlm47/VidClip.git
cd VidClip
```

Analyze a downloaded video (replace the example path):

```bash
python vidclip.py analyze ~/storage/shared/Download/your-video.mp4
```

Choose up to five clips with a 120-second ceiling:

```bash
python vidclip.py analyze ~/storage/shared/Download/your-video.mp4 --clips 5 --max-duration 120
```

Create vertical clips:

```bash
python vidclip.py analyze ~/storage/shared/Download/your-video.mp4 --aspect vertical
```

Choose a shorter ceiling:

```bash
python vidclip.py analyze ~/storage/shared/Download/your-video.mp4 --max-duration 60 --clips 5
```

Outputs are written under `output/<video-name>/` by default. Use `--output /path/to/folder` to choose another location.

## How the baseline works

1. FFprobe reads duration, dimensions, and stream information.
2. FFmpeg's `silencedetect` filter finds quiet intervals.
3. VidClip converts the remaining active intervals into candidate windows.
4. Candidates are scored using active-audio coverage and usable duration.
5. Greedy overlap suppression keeps the best distinct moments.
6. FFmpeg exports each selected range and a machine-readable report.

**Important limitation:** audio activity is only a proxy. A loud moment is not necessarily interesting, and a quiet explanation may be excellent. This version does not transcribe words or understand context. The report labels its score as a baseline technical score, not a viral score.

## Planned upgrades

- [ ] Sentence-aware transcription provider (optional; local or free hosted provider).
- [ ] Semantic highlight ranking: hook, payoff, story completeness, useful information, context.
- [ ] Scene-change and motion signals as independent, explainable score components.
- [ ] Caption generation and editable subtitle files.
- [ ] Safer vertical reframing; speaker/subject tracking as an optional heavier feature.
- [ ] Local browser review dashboard and Android-friendly import workflow.
- [ ] Trend Radar with dated sources, niche filters, and freshness labels.
- [ ] User feedback loop that learns which selected clips perform well.
- [ ] Automated tests and a small licensed/public-domain sample fixture set.

## Design principles

- **No mandatory AI:** core analysis and export must still work when every AI provider is unavailable.
- **No surprise costs:** no paid fallback, metered service, or billing path.
- **No destructive edits:** source media is never overwritten.
- **Explain uncertainty:** distinguish measured signals from semantic judgments.
- **Human approval:** exports are created locally; publishing remains user-controlled.
- **Rights-aware:** only process and republish footage you own or are licensed/authorized to use. Downloading a video does not grant republication rights. No DRM circumvention.

## Competitor research

See [docs/COMPETITOR-RESEARCH.md](docs/COMPETITOR-RESEARCH.md) for the comparison of AutoClip and VideoHighlighter and the design decisions VidClip adopts.

## License

MIT. See [LICENSE](LICENSE).
