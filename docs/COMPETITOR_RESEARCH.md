# Open-source clipping tool research

Research snapshot: 10 November 2026. This is a feature and architecture comparison based on public repository documentation and README files, not a full audit of every source file or benchmark.

## Projects reviewed

### 1. ClipsAI — https://github.com/ClipsAI/clipsai

**Strengths**
- Transcript-driven clip discovery for podcasts, interviews, speeches, and narrative audio.
- Word-level timestamps through WhisperX.
- Aspect-ratio conversion and speaker-aware reframing using Pyannote.

**Trade-offs for VidClip**
- The documented pipeline depends on WhisperX and additional ML components.
- Speaker diarization and reframing require a Hugging Face token.
- Its README positions it for audio-centric narrative material.

**VidClip decision**
- Adopt transcript-first semantic selection as a future optional analysis layer.
- Do not make WhisperX, GPU access, or hosted model tokens mandatory.
- Keep the base engine functional on low-memory Android hardware.

### 2. Auto-Editor — https://github.com/WyattBlue/auto-editor

**Strengths**
- Automated editing based on audio loudness and motion.
- Adjustable silence thresholds and margins.
- Multiple edit signals and exports to professional editing timelines.

**Trade-offs for VidClip**
- It is an editing/automation engine, not a complete semantic viral-highlight discovery product.
- Silence and motion alone cannot determine whether a story, joke, or explanation has a satisfying ending.

**VidClip decision**
- Adopt audio activity detection, configurable thresholds, boundary padding, and explainable segmentation.
- Add semantic ranking separately rather than treating loudness as virality.

### 3. OpenShorts — https://github.com/mutonby/openshorts

**Strengths**
- Integrated workflow: clip generation, vertical layouts, captions, and other creator tooling.
- Documents stacked-speaker layouts and adaptive framing.
- Local self-hosting option and API/MCP-oriented workflow.

**Trade-offs for VidClip**
- Its documented self-hosted setup expects Docker and 8GB+ RAM, plus user-supplied AI/media service keys.
- That is a poor fit for a 3GB Android tablet and a strict free-first requirement.

**VidClip decision**
- Learn from its integrated review-to-export workflow and layout decisions.
- Keep VidClip's initial architecture single-process, local, and light.
- Defer multi-speaker layout detection until the core pipeline is stable.

### 4. YT Short Clipper — https://github.com/jipraks/yt-short-clipper

**Strengths**
- Transcript-based highlight selection with configurable AI direction.
- 58–120 second clip range, word-by-word captions, portrait reframing, and hook overlays.
- Documents provider configuration and data/network behavior.

**Trade-offs for VidClip**
- The documented app is Windows-only and uses a React/Tauri/Rust desktop shell with a Python sidecar.
- It depends on YouTube subtitle/download workflows and an AI provider for its highlight workflow.
- Its build requirements are unsuitable for the target Android tablet.

**VidClip decision**
- Adopt the useful idea of 58–120 second story clips, custom editorial direction, caption timing, and transparent provider configuration.
- Prioritize local-file import and Android/Termux compatibility.
- Never require YouTube cookies or downloading a URL to use the core clipper.

## VidClip differentiation

1. **Offline-first:** candidate discovery and export work without AI, accounts, network access, or API keys.
2. **Graceful degradation:** optional AI failures fall back to deterministic analysis; no paid fallback or surprise billing.
3. **Long-enough moments:** user can set a maximum up to 120 seconds, with natural ending preservation prioritized over fixed duration.
4. **Explainable scores:** show each signal and uncertainty. Do not promise virality.
5. **Low-resource architecture:** standard-library Python and FFmpeg first; optional heavy features remain separate.
6. **Local-first privacy:** source videos and transcripts stay on-device unless the user explicitly chooses an external provider.
7. **Human approval:** publishing and account actions are not automatic by default.

## Research links

- ClipsAI README: https://github.com/ClipsAI/clipsai
- Auto-Editor README: https://github.com/WyattBlue/auto-editor
- OpenShorts README: https://github.com/mutonby/openshorts
- YT Short Clipper README: https://github.com/jipraks/yt-short-clipper

## Review limitations

Repository READMEs describe intended capabilities, setup, and constraints; they do not prove current performance on identical hardware or source videos. No competitor code has been copied into VidClip. The implementation is original and uses FFmpeg through its command-line interface.
