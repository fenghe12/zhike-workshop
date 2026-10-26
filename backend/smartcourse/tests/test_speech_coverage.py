import unittest
from app.speech_coverage import coverage_report


class ShortSpeechCoverageTests(unittest.TestCase):
    def test_unrelated_short_speech_does_not_pass(self):
        result = coverage_report('输入是九，输出是一。', [{'text': '今天天气晴朗。'}])
        self.assertFalse(result['passed'])

    def test_short_speech_accepts_ordinary_number_transcription_variation(self):
        result = coverage_report('输入是9。', [{'text': '输入是九。'}])
        self.assertTrue(result['passed'])
