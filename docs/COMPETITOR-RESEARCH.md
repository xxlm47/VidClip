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
