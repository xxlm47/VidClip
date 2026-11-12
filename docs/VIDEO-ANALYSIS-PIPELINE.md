# Story-aware analysis and export QA

## What this update adds

VidClip accepts an optional timed subtitle sidecar (.srt or .vtt) and uses transparent lexical evidence to improve candidate ranking. It also validates every exported clip with FFprobe before reporting success.

Transcript signals include subtitle coverage, word density, question and exclamation marks, a small set of hook/payoff phrases, and emotion-related words. They are heuristics: they do not prove emotion, story quality, factual accuracy, or virality.

## Workflow

1. Probe the source and confirm usable streams.
2. Detect active audio and generate candidate windows.
3. If --transcript is supplied, parse timed subtitle cues and attach transcript evidence to each candidate.
4. Rank with technical audio evidence and transcript evidence while retaining both scores independently in the report.
5. Suppress overlapping candidates and export selected clips.
6. Run FFprobe on every export and verify duration, video stream, and expected audio stream before marking the clip valid.
7. Write JSON and CSV reports, including limitations and evidence.

## Example

```bash
python vidclip.py analyze input.mp4 --transcript input.srt --clips 5 --max-duration 120
```

Without a sidecar, VidClip remains fully offline and uses its audio-activity baseline. No AI provider, account, model download, or paid API is needed.

## Current limitations

- Subtitle files must already exist; this update does not transcribe audio.
- Lexical cues can miss sarcasm, context, speaker intent, and non-English content.
- The current vertical export is a center crop, not subject tracking.
- Scene understanding, emotion recognition, and trend discovery are not claimed as implemented.
- Human review remains required before publishing, especially where minors, sensitive events, allegations, or identifiable people appear.
