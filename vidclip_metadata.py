"""Offline, transcript-grounded TikTok metadata for VidClip.

Titles quote or summarize words actually present in the selected clip when a
timed transcript is available. Without a transcript, output is explicitly
marked as a filename-based draft rather than pretending to understand video.
"""
import re
from collections import Counter
from pathlib import Path

STOPWORDS = {
    "about", "after", "again", "against", "also", "because", "been", "before",
    "being", "between", "could", "does", "doing", "down", "during", "each",
    "from", "have", "having", "here", "hers", "him", "his", "into", "just",
    "like", "more", "most", "much", "must", "over", "same", "should", "some",
    "such", "than", "that", "their", "them", "then", "there", "these", "they",
    "this", "those", "through", "under", "very", "were", "what", "when",
    "where", "which", "while", "will", "with", "would", "your", "you're",
    "you", "the", "and", "for", "are", "was", "but", "not", "you", "our",
    "out", "all", "can", "one", "who", "why", "how", "its", "it's", "she",
    "her", "him", "his", "they", "them", "their", "got", "get", "gotta",
    "yeah", "okay", "yes", "well", "now", "then", "thing", "things"
}
TAG_MAP = {
    "police": "#Police", "officer": "#Police", "cops": "#Police",
    "traffic": "#TrafficStop", "stop": "#TrafficStop", "bodycam": "#Bodycam",
    "body": "#Bodycam", "court": "#Court", "judge": "#Court",
    "lawyer": "#Law", "legal": "#Law", "arrest": "#Arrest",
    "arrested": "#Arrest", "crime": "#Crime", "criminal": "#Crime",
    "news": "#News", "breaking": "#BreakingNews", "drugs": "#DrugAwareness",
    "drug": "#DrugAwareness", "children": "#ChildSafety", "child": "#ChildSafety",
    "kids": "#ChildSafety", "medic": "#FirstResponders", "ambulance": "#FirstResponders",
    "hospital": "#FirstResponders", "fire": "#FirstResponders",
    "rescue": "#Rescue", "accident": "#事故", "crash": "#Crash",
    "car": "#Cars", "vehicle": "#Cars", "school": "#Education",
    "money": "#Money", "business": "#Business", "sports": "#Sports",
    "football": "#Football", "basketball": "#Basketball",
    "relationship": "#Relationships", "wife": "#Relationships",
    "husband": "#Relationships", "family": "#Family"
}
GENERIC_TAGS = ("#VideoClip", "#WatchThis")


def _clean_name(value):
    words = re.findall(r"[A-Za-z0-9]+", Path(value).stem.replace("_", " ").replace("-", " "))
    return " ".join(words).strip()


def _clip_text(cues, start, end):
    parts = [cue.text.strip() for cue in cues
             if cue.end > start and cue.start < end and cue.text.strip()]
    return re.sub(r"\s+", " ", " ".join(parts)).strip()


def _title_from_transcript(text, fallback):
    if not text:
        return "A key moment from " + fallback if fallback else "A key moment worth watching"
    # Prefer a complete spoken sentence; never invent an event absent from speech.
    sentences = re.split(r"(?<=[.!?])\s+", text)
    usable = [s.strip(" -\t") for s in sentences if len(s.strip()) >= 18]
    candidate = max(usable, key=lambda s: min(len(s), 100)) if usable else text
    candidate = re.sub(r"\s+", " ", candidate).strip(' "'')
    if len(candidate) > 88:
        candidate = candidate[:85].rsplit(" ", 1)[0].rstrip(" ,;:-") + "..."
    if candidate and candidate[-1] not in ".!?":
        candidate += "..."
    return candidate[:90]


def _hashtags(text, source_name):
    combined = (text + " " + _clean_name(source_name)).lower()
    tokens = re.findall(r"[a-z][a-z0-9]{2,}", combined)
    counts = Counter(token for token in tokens if token not in STOPWORDS)
    tags = []
    for token, _count in counts.most_common():
        mapped = TAG_MAP.get(token)
        if mapped and mapped not in tags:
            tags.append(mapped)
        if len(tags) >= 5:
            break
    # Use meaningful transcript keywords only when they are not already covered.
    for token, _count in counts.most_common(8):
        tag = "#" + token.title().replace("_", "")
        if tag.lower() not in {x.lower() for x in tags} and len(tag) <= 24:
            tags.append(tag)
        if len(tags) >= 5:
            break
    for tag in GENERIC_TAGS:
        if len(tags) >= 5:
            break
        if tag not in tags:
            tags.append(tag)
    return tags[:5]


def build_clip_metadata(cues, start, end, source_name, clip_index):
    text = _clip_text(cues or [], start, end)
    fallback = _clean_name(source_name)
    transcript_based = bool(text)
    title = _title_from_transcript(text, fallback)
    hashtags = _hashtags(text, source_name)
    caption = title
    if hashtags:
        caption += "\n\n" + " ".join(hashtags)
    return {
        "clip_index": int(clip_index),
        "title": title,
        "caption": caption,
        "hashtags": hashtags,
        "metadata_basis": "timed_transcript" if transcript_based else "source_filename_fallback",
        "transcript_text_available": transcript_based,
        "review_note": (
            "Draft generated from words in this clip; verify names and context before posting."
            if transcript_based else
            "No transcript available. This is a filename-based placeholder; review and edit before posting."
        )
    }


def write_metadata_files(output_dir, items):
    output_dir = Path(output_dir)
    (output_dir / "titles_and_hashtags.txt").write_text(
        "\n\n".join(
            "CLIP {index:02d}\nTITLE: {title}\nHASHTAGS: {tags}\nCAPTION:\n{caption}\nNOTE: {note}".format(
                index=item["clip_index"], title=item["title"],
                tags=" ".join(item["hashtags"]), caption=item["caption"],
                note=item["review_note"])
            for item in items
        ) + "\n", encoding="utf-8")
    (output_dir / "clip_metadata.json").write_text(
        __import__("json").dumps(items, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
