import unittest

import vidclip


class VidClipBaselineTests(unittest.TestCase):
    def test_active_regions_are_complement_of_silence(self):
        regions = vidclip.active_regions([(2.0, 3.0), (5.0, 6.0)], 8.0)
        self.assertEqual(regions, [(0.0, 2.0), (3.0, 5.0), (6.0, 8.0)])

    def test_candidate_duration_never_exceeds_limit(self):
        regions = [(0.0, 40.0), (45.0, 95.0)]
        candidates = vidclip.make_candidates(regions, 100.0, 15.0, 60.0)
        self.assertTrue(candidates)
        self.assertTrue(all(c.duration <= 60.001 for c in candidates))

    def test_selection_avoids_duplicate_overlapping_moments(self):
        candidates = [
            vidclip.Candidate(0, 30, 28, .93, 90, []),
            vidclip.Candidate(2, 32, 28, .93, 89, []),
            vidclip.Candidate(60, 90, 28, .93, 88, []),
        ]
        selected = vidclip.choose_non_overlapping(candidates, 2, 100.0)
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0].start, 0)
        self.assertEqual(selected[1].start, 60)

    def test_candidate_scan_covers_later_parts_of_long_video(self):
        candidates = vidclip.make_candidates([(0.0, 300.0)], 300.0, 15.0, 120.0)
        self.assertTrue(any(candidate.start > 150.0 for candidate in candidates))

    def test_overlap_seconds_counts_only_active_audio(self):
        self.assertEqual(vidclip.overlap_seconds(0, 30, [(0, 10), (20, 30)]), 20)

    def test_candidate_score_rewards_active_coverage(self):
        quiet = vidclip.make_candidates([(0, 10), (20, 30)], 30, 15, 30)
        active = vidclip.make_candidates([(0, 30)], 30, 15, 30)
        self.assertTrue(quiet and active)
        self.assertGreater(max(c.score for c in active),
                           max(c.score for c in quiet))

    def test_clip_filename_keeps_mp4_extension(self):
        name = vidclip.make_clip_filename(2, 123.4)
        self.assertEqual(name, "clip_02_123_4s.mp4")
        self.assertTrue(name.endswith(".mp4"))

    def test_silence_only_input_has_no_active_regions(self):
        self.assertEqual(vidclip.active_regions([(0.0, 20.0)], 20.0), [])


if __name__ == "__main__":
    unittest.main()
