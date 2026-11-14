import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from vidclip_metadata import build_clip_metadata, write_metadata_files


class VidClipMetadataTests(unittest.TestCase):
    def test_transcript_produces_clip_specific_title_and_relevant_tags(self):
        cues = [
            SimpleNamespace(start=10.0, end=20.0,
                            text="The police officer explains why this traffic stop happened."),
            SimpleNamespace(start=21.0, end=30.0,
                            text="The driver asks what happens next.")
        ]
        result = build_clip_metadata(cues, 0, 40, "random_video.mp4", 1)
        self.assertEqual(result["metadata_basis"], "timed_transcript")
        self.assertTrue(result["title"])
        self.assertIn("#Police", result["hashtags"])
        self.assertLessEqual(len(result["hashtags"]), 5)

    def test_missing_transcript_is_honestly_marked_as_fallback(self):
        result = build_clip_metadata([], 0, 90, "Routine-Stop.mp4", 2)
        self.assertEqual(result["metadata_basis"], "source_filename_fallback")
        self.assertIn("Routine Stop", result["title"])
        self.assertIn("No transcript", result["review_note"])

    def test_writes_copy_ready_text_and_json(self):
        items = [build_clip_metadata([], 0, 90, "test.mp4", 1)]
        with tempfile.TemporaryDirectory() as directory:
            write_metadata_files(directory, items)
            text_file = Path(directory) / "titles_and_hashtags.txt"
            json_file = Path(directory) / "clip_metadata.json"
            self.assertTrue(text_file.is_file())
            self.assertTrue(json_file.is_file())
            self.assertIn("TITLE:", text_file.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
