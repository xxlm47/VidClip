# Automatic subtitles and clip captions

VidClip can add readable captions to every selected clip.

## Subtitle source priority

1. `--transcript file.srt`: use a supplied SRT or WebVTT file.
2. `--whisper-model /path/to/model.bin`: transcribe the source locally with whisper.cpp when no sidecar is supplied.
3. If neither is supplied, VidClip does not invent dialogue. It exports without captions and explains that transcription was not enabled.

VidClip first tries to extract an embedded text subtitle track from the source container. Image-based subtitle tracks (such as PGS/DVD subtitles) are skipped; if no usable text track is found, it can fall back to local Whisper transcription when a model is supplied.

## Local Whisper setup

Build/install the whisper.cpp command-line program so `whisper-cli` is on PATH. Download a compatible model to local storage yourself. No model is downloaded by VidClip.

Example:

```bash
python vidclip.py analyze input.mp4 --whisper-model ~/models/ggml-base.en.bin --clips 5 --max-duration 120
```

Use `--whisper-cli /path/to/whisper-cli` if the executable has another name or is not on PATH. Audio is converted to mono 16 kHz WAV before transcription. On Android, transcription can be slow; a smaller quantized model is generally more practical than a large model. Actual speed and memory use depend on the phone.

## Caption output

Default: `--subtitle-mode burn`. Captions are burned into the MP4, so they remain visible in social apps even when viewers have sound off. VidClip also writes a matching per-clip SRT next to each MP4.

- `--subtitle-mode sidecar`: write editable per-clip SRT files without changing the picture.
- `--subtitle-mode none`: do not write or burn clip subtitles.

Each clip's SRT is trimmed to its exact time range and timestamps are rebased to start at zero. Burned captions are rendered by FFmpeg's subtitles filter and therefore require an FFmpeg build with libass support.

## Accuracy and review

Speech recognition can mishear names, accents, overlapping speakers, slang, technical terms, and noisy audio. Always review captions before publishing, especially when the video includes allegations, medical information, minors, or other sensitive subjects. Captions improve accessibility and comprehension but do not establish that spoken claims are true.

This feature is optional and offline-first. It does not use a paid API, upload the video, or automatically download a model.
