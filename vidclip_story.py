"""Optional SRT/WebVTT transcript evidence for VidClip. No model or network required."""
import re
from dataclasses import dataclass
from pathlib import Path

@dataclass
class Cue:
    start: float
    end: float
    text: str

TIMESTAMP = re.compile(r"(?P<start>(?:\d{2}:)?\d{2}:\d{2}[,.]\d{3})\s*-->\s*(?P<end>(?:\d{2}:)?\d{2}:\d{2}[,.]\d{3})")
TAG = re.compile(r"<[^>]+>")
HOOK_TERMS = ("what happened", "here's why", "the reason", "watch what", "look at", "how did", "why would", "what if")
PAYOFF_TERMS = ("but then", "until", "turns out", "found out", "the result", "in the end", "that's when")
EMOTION_TERMS = ("scared", "angry", "crying", "shocked", "terrified", "furious", "worried", "upset", "surprised", "laughing", "screaming")

def _seconds(value):
    parts = value.replace(",", ".").split(":")
    if len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    hours, minutes, seconds = parts
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

def parse_subtitles(path):
    source = Path(path)
    if not source.is_file():
        raise ValueError("Transcript sidecar does not exist: " + str(source))
    lines = source.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cues, index = [], 0
    while index < len(lines):
        match = TIMESTAMP.search(lines[index])
        if not match:
            index += 1
            continue
        start, end = _seconds(match.group("start")), _seconds(match.group("end"))
        index += 1
        body = []
        while index < len(lines) and lines[index].strip():
            body.append(lines[index].strip())
            index += 1
        text = re.sub(r"\s+", " ", TAG.sub("", " ".join(body))).strip()
        if text and end > start:
            cues.append(Cue(start, end, text))
        index += 1
    if not cues:
        raise ValueError("No valid subtitle cues found. Provide a timed SRT or WebVTT file.")
    return cues

def score_transcript_window(start, end, cues):
    inside = [cue for cue in cues if cue.end > start and cue.start < end]
    if not inside:
        return {"score": 0.0, "cue_count": 0, "signals": {}, "reasons": ["no transcript cues overlap this window"]}
    text = " ".join(cue.text for cue in inside).lower()
    words = re.findall(r"\b[\w']+\b", text)
    duration = max(1.0, end - start)
    coverage = min(1.0, sum(max(0.0, min(end, c.end) - max(start, c.start)) for c in inside) / duration)
    hooks = sum(1 for term in HOOK_TERMS if term in text)
    payoffs = sum(1 for term in PAYOFF_TERMS if term in text)
    emotion = sum(1 for term in EMOTION_TERMS if term in text)
    questions, exclamations = text.count("?"), text.count("!")
    density = min(1.0, len(words) / max(1.0, duration * 2.2))
    signals = {"subtitle_coverage": round(coverage, 3), "word_density": round(density, 3),
               "hook_phrase_hits": hooks, "payoff_phrase_hits": payoffs,
               "question_marks": questions, "exclamation_marks": exclamations,
               "emotion_word_hits": emotion, "cue_count": len(inside)}
    score = 100.0 * (0.25 * coverage + 0.20 * density + 0.15 * min(1.0, hooks / 2.0)
        + 0.15 * min(1.0, payoffs / 2.0) + 0.10 * min(1.0, questions / 2.0)
        + 0.05 * min(1.0, exclamations / 2.0) + 0.10 * min(1.0, emotion / 2.0))
    reasons = [str(len(inside)) + " timed subtitle cues", "{:.0f}% subtitle-time coverage".format(coverage * 100)]
    for key, label in (("hook_phrase_hits", "hook phrase"), ("payoff_phrase_hits", "payoff phrase"),
                       ("question_marks", "question"), ("emotion_word_hits", "emotion-word")):
        if signals[key]:
            reasons.append("{} {} signal(s)".format(signals[key], label))
    return {"score": round(score, 1), "cue_count": len(inside), "signals": signals, "reasons": reasons}

def attach_transcript_scores(candidates, cues):
    for candidate in candidates:
        result = score_transcript_window(candidate.start, candidate.end, cues)
        candidate.story_score = result["score"]
        candidate.story_analysis = result
