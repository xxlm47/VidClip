import tempfile
import unittest
from pathlib import Path

from vidclip_story import Cue
from vidclip_subtitles import write_clip_srt, burn_subtitles_filter


class SubtitleExportTests(unittest.TestCase):
    def test_clip_srt_trims_and_rebases_cues(self):
        cues = [
            Cue(8.0, 12.0, "Before and during"),
            Cue(12.0, 15.0, "After the clip"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "clip.srt"
            count = write_clip_srt(target, cues, 10.0, 13.0)
            text = target.read_text(encoding="utf-8")
        self.assertEqual(count, 2)
        self.assertIn("00:00:00,000 --> 00:00:02,000", text)
        self.assertIn("00:00:02,000 --> 00:00:03,000", text)
        self.assertIn("Before and during", text)
        self.assertIn("After the clip", text)

    def test_burn_filter_escapes_special_path_characters(self):
        with tempfile.TemporaryDirectory(prefix="vidclip:caption,") as folder:
            path = Path(folder) / "it's.srt"
            filter_value = burn_subtitles_filter(path)
        self.assertIn("\\:", filter_value)
        self.assertIn("\\,", filter_value)
        self.assertIn("\\'", filter_value)


if __name__ == "__main__":
    unittest.main()
