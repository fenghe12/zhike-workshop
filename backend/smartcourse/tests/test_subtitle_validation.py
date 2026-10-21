import unittest
from app.subtitle_validation import validate_timestamps


class TimestampTests(unittest.TestCase):
    def test_preserves_measured_pauses(self):
        values = [{"text": "Hello", "start": 0.3, "end": 1.2},
                  {"text": "世界", "start": 2.1, "end": 3.4}]
        validate_timestamps(values, 4)
        self.assertEqual(values[1]["start"], 2.1)

    def test_rejects_unusable_alignment(self):
        cases = [[], [{"text": "", "start": 0, "end": 1}],
                 [{"text": "x", "start": -1, "end": 1}],
                 [{"text": "x", "start": 2, "end": 1}],
                 [{"text": "x", "start": 0, "end": 5}],
                 [{"text": "x", "start": 0, "end": float("nan")}],
                 [{"text": "a", "start": 0, "end": 2}, {"text": "b", "start": 1, "end": 3}]]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                validate_timestamps(case, 4)
