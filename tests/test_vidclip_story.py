import tempfile
import unittest
from pathlib import Path
import vidclip_story

class TranscriptAnalysisTests(unittest.TestCase):
    def test_parse_srt_and_score_hook_payoff(self):
        content = "1\n00:00:01,000 --> 00:00:03,000\nWhat happened here?\n\n2\n00:00:03,000 --> 00:00:05,000\nBut then they found out!\n"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.srt"
            path.write_text(content, encoding="utf-8")
            cues = vidclip_story.parse_subtitles(str(path))
        self.assertEqual(len(cues), 2)
        result = vidclip_story.score_transcript_window(0, 8, cues)
        self.assertGreater(result["score"], 0)
        self.assertEqual(result["signals"]["question_marks"], 1)
        self.assertEqual(result["signals"]["payoff_phrase_hits"], 1)

    def test_invalid_sidecar_fails_clearly(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "empty.srt"
            path.write_text("no timestamps", encoding="utf-8")
            with self.assertRaises(ValueError):
                vidclip_story.parse_subtitles(str(path))

    def test_webvtt_markup(self):
        content = "WEBVTT\n\n00:00:01.000 --> 00:00:02.500\n<c>Look at this</c>\n"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "sample.vtt"
            path.write_text(content, encoding="utf-8")
            cues = vidclip_story.parse_subtitles(str(path))
        self.assertEqual(cues[0].text, "Look at this")
        self.assertAlmostEqual(cues[0].end, 2.5)

if __name__ == "__main__":
    unittest.main()
