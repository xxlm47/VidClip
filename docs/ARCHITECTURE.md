# VidClip architecture

## Current foundation

\`\`\`text
Local video file
    |
    v
FFprobe metadata inspection
    |
    v
FFmpeg silence detection
    |
    v
Active-region segmentation
    |
    v
Candidate windows (15–120 seconds)
    |
    v
Provisional score + explanation
    |
    +----> analysis.json
    |
    v
FFmpeg H.264 export
    |
    v
Local clips + manifest.json
\`\`\`

The current implementation has no mandatory third-party Python dependencies.

## Planned analysis pipeline

Each analyzer should be an independent component that returns structured evidence:

- Audio activity: speech/non-silence regions, loudness changes, pauses.
- Transcription: words, timestamps, sentence boundaries, language.
- Semantic analysis: hook, topic, story progression, context, payoff, conclusion.
- Visual analysis: scene changes, motion, face/speaker positions, framing.
- Trend matching: niche, topic, format, dated trend evidence.

Candidate scoring should combine evidence with explicit weights. Missing evidence must be marked unknown, not silently scored as zero or fabricated.

## AI provider contract (planned)

A provider adapter should expose:
- \`is_available()\`
- \`analyze_transcript(transcript, settings)\`
- \`health()\`
- A normalized result schema with candidate timestamps, rationale, and confidence.

Provider order must be user-configurable. A provider failure, quota response, network error, or invalid output must:
1. Be recorded in the project log.
2. Avoid retry loops.
3. Avoid trying any paid provider.
4. Fall back to local heuristics.
5. Keep the user able to finish the project.

API keys must never be committed to the repository or written to logs. External analysis must be opt-in and disclose what text is sent.

## Resource policy

- One source video per analysis job by default.
- Avoid loading full video frames into Python memory.
- Use FFmpeg for media decoding and encoding.
- Keep transcript/model downloads optional.
- Do not bundle large local models in the base installation.
- Allow cancellation and preserve partial analysis metadata.

## Export policy

- MP4/H.264 + AAC for broad compatibility.
- 9:16 centered crop or original aspect ratio in the foundation.
- Future layouts: blurred background, subject-aware crop, speaker split-screen.
- Captions should be editable sidecar files before they are burned in.
- Keep the source video unchanged.

## Safety boundaries

No autonomous publishing, credential collection, bypassing platform access controls, or unrestricted shell commands. Require explicit confirmation for publishing, account changes, payments, and outbound messages.
