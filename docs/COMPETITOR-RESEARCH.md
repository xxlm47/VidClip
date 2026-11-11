# Competitor research

Research checked 10 November 2026. This is a product/architecture comparison based on public repository documentation, not a benchmark of their code or output quality.

## AutoClip — artbyjazi/autoclip

Repository: https://github.com/artbyjazi/autoclip

Documented strengths:
- End-to-end ingest → prepare → transcribe → highlight selection → reframing → captions → export.
- Local Whisper + Ollama mode and optional hosted providers.
- Speaker-aware vertical reframing, multiple caption styles, review UI.
- Stage artifacts support retrying a failed job.
- Explicit statement that clip quality and reframe quality still need validation against fixed acceptance sets.

Trade-offs for VidClip:
- Requires Python 3.11/3.12, Node for UI build, MediaPipe, and optional Whisper/diarization dependencies.
- Its own documentation describes GPU/model setup and resource requirements that do not match a 3 GB Android tablet.

VidClip response:
- Keep core in Python standard library + FFmpeg.
- Make transcription and LLM selection provider interfaces optional.
- Persist each stage's outputs so future runs can resume.
- Never require a model to export a clip.

## VideoHighlighter — Aseiel/VideoHighlighter

Repository: https://github.com/Aseiel/VideoHighlighter

Documented strengths:
- Multi-signal scoring across scene, motion, audio, objects, actions, and transcript.
- Per-signal score explanations and reports.
- Local analysis with no API key required for its basic pipeline.
- Composition rules that can be adapted to different footage types.

Trade-offs for VidClip:
- It is a local desktop application for Windows, macOS, and Linux, with a broader detector/model ecosystem.
- Its full feature set is far beyond what should be loaded on a low-memory Android device.

VidClip response:
- Start with inexpensive measurable signals.
- Store each signal independently in the report.
- Mark unavailable signals as unknown rather than inventing scores.
- Add scene and motion analysis as optional FFmpeg stages.

## Product decisions

1. Android-first and low-memory by default.
2. Offline core, no required API key, no paid fallback.
3. Maximum 120-second clips; never pad a short moment just to reach two minutes.
4. Prefer sentence/story-aware boundaries once transcription exists.
5. Score explanations and uncertainty are part of the product, not debugging details.
6. Export locally; do not automate account access or publishing without explicit approval.

## Sources

- https://github.com/artbyjazi/autoclip
- https://github.com/Aseiel/VideoHighlighter
- https://ffmpeg.org/ffmpeg-filters.html


## Additional projects reviewed

### Clipper — jameselle/clipper

Repository: https://github.com/jameselle/clipper

Documented strengths:
- Transcript-first selection with a strong opening hook and payoff.
- Word-timed captions using whisper.cpp.
- Silence trimming that is designed not to cut words.
- Automated export QA: sound, dead air, black frames, rotation, aspect ratio, and word retention.
- A review page for timestamped visual notes.

VidClip response:
- Add a formal export QA stage and transcript-aligned boundaries before claiming a clip is ready.
- Preserve source words and sentence endings; do not optimize only for loudness.
- Use cached intermediate artifacts so re-analysis is cheaper.

### Chopify — mehbul/chopify

Repository: https://github.com/mehbul/chopify

Documented strengths:
- Local browser dashboard plus CLI.
- Resumable batch projects, editable captions/SRT, brand presets, and semantic search.
- Automated tests that can run without speech models or Ollama.

VidClip response:
- Build the browser dashboard after the CLI pipeline is stable.
- Keep project/job artifacts resumable and make caption edits reviewable.
- Test the core without requiring a model or network access.

### irosadie/clipper

Repository: https://github.com/irosadie/clipper

Documented strengths:
- Podcast-oriented transcript heuristics using laughter, excitement words, exclamations, and speaking-rate changes.
- Lightweight CLI workflow for proposing moments.

VidClip response:
- Add configurable content profiles (podcast, gaming, sports, tutorial) once transcripts exist.
- Treat these heuristics as evidence signals, not proof of quality.

### Steezy-code/clipper

Repository: https://github.com/Steezy-code/clipper

Documented strengths:
- Clear staged architecture: transcription, local LLM selection, silence tightening, face tracking, captions, FFmpeg export.
- Explicit discussion of model and face-tracking limitations.

VidClip response:
- Keep each stage replaceable and independently testable.
- Avoid face tracking in the default Android path; provide simpler crop modes first.

## Consolidated feature priorities for VidClip

| Priority | Capability | Reason |
|---|---|---|
| P0 | Reliable import, probe, clip detection, export, reports | Core must work on the target tablet |
| P0 | Accurate clip boundaries and overlap removal | Avoid broken endings and duplicate clips |
| P0 | Export validation (duration, audio, video, dimensions) | Catch corrupt or unusable files |
| P1 | Optional transcription with word timestamps | Enables semantic selection and sentence-safe trims |
| P1 | Review UI and editable clip boundaries | Human review is faster than blind automation |
| P1 | Caption files and burned-in caption presets | Platform-ready finishing |
| P2 | Scene/motion scoring and vertical subject tracking | Improve visual quality without bloating the baseline |
| P2 | Content profiles and trend research | Context-aware suggestions by niche and date |

The research supports a staged product, not a monolithic model-heavy application. The immediate baseline is intentionally narrow; the next quality leap should be transcription plus sentence-aware boundaries, not an oversized dashboard.
