import unittest

from vidclip.core import VidClipError, active_regions, find_candidates


class CandidateTests(unittest.TestCase):
    def test_active_regions_invert_silence(self):
        self.assertEqual(active_regions(40, [(10, 12), (20, 25)]),
                         [(0, 10), (12, 20), (25, 40)])

    def test_nearby_regions_merge(self):
        self.assertEqual(active_regions(30, [(10, 10.5)], merge_gap=2), [(0, 30)])

    def test_candidates_obey_120_second_limit(self):
        result = find_candidates(300, [(50, 55), (110, 115), (170, 175)],
                                 min_duration=15, max_duration=120, max_clips=5)
        self.assertTrue(all(item.duration <= 120 for item in result))

    def test_results_do_not_overlap(self):
        result = find_candidates(240, [(40, 45), (100, 105), (160, 165)],
                                 min_duration=20, max_duration=90, max_clips=5)
        for index, first in enumerate(result):
            for second in result[index + 1:]:
                self.assertFalse(first.start < second.end and second.start < first.end)

    def test_candidate_score_penalizes_silence_inside_window(self):
        result = find_candidates(100, [(20, 50)], min_duration=60,
                                 max_duration=60, max_clips=5)
        self.assertEqual(len(result), 1)
        self.assertAlmostEqual(result[0].active_ratio, 0.7, places=2)

    def test_all_silence_produces_no_candidates(self):
        result = find_candidates(100, [(0, 100)], min_duration=15,
                                 max_duration=120, max_clips=5)
        self.assertEqual(result, [])

    def test_invalid_duration_is_rejected(self):
        with self.assertRaises(VidClipError):
            find_candidates(60, [], min_duration=10, max_duration=121)

    def test_long_uninterrupted_speech_is_split(self):
        result = find_candidates(300, [], min_duration=30, max_duration=120, max_clips=5)
        self.assertTrue(result)
        self.assertTrue(all(30 <= item.duration <= 120 for item in result))


if __name__ == "__main__":
    unittest.main()
