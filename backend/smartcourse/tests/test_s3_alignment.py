import tempfile
import unittest
from pathlib import Path

from agents.s3_tts_agent import WhisperAligner, format_srt_time
from agents.cosyvoice_engine import CosyVoiceEngine, normalize_language


class AlignmentContractTests(unittest.TestCase):
    def test_business_language_codes_reach_speech_backend(self):
        for code in ["zh-CN", "en-US", "ja-JP", "ko-KR", "de-DE", "fr-FR", "ru-RU"]:
            self.assertEqual(normalize_language(code), code.split('-')[0])
    def test_russian_math_text_is_prepared_for_speech(self):
        from agents.cosyvoice_engine import prepare_spoken_text
        self.assertIn('равно',prepare_spoken_text('z = 1','ru'))
    def test_subtitle_millisecond_rounding_carries_seconds(self):
        self.assertEqual(format_srt_time(59.9999), "00:01:00,000")
        self.assertEqual(format_srt_time(3600.125), "01:00:00,125")
    def test_empty_asr_result_is_failure(self):
        class EmptyRecognizer:
            def transcribe(self, *args, **kwargs):
                return {"segments": []}
        aligner = WhisperAligner()
        aligner._model = EmptyRecognizer()
        with self.assertRaisesRegex(ValueError, "时间戳"):
            aligner.get_sentence_timestamps("unused.wav", "de")

    def test_segment_timestamps_are_retained(self):
        class SegmentRecognizer:
            def transcribe(self, *args, **kwargs):
                return {"segments": [{"text": " Guten Tag. ", "start": 0.42, "end": 1.81}]}
        aligner = WhisperAligner()
        aligner._model = SegmentRecognizer()
        self.assertEqual(aligner.get_sentence_timestamps("unused.wav", "de"),
                         [{"text": "Guten Tag.", "start": 0.42, "end": 1.81}])

    def test_missing_reference_fails_before_model_load(self):
        engine = CosyVoiceEngine()
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "参考音频"):
                engine.synthesize("Hello", str(Path(temporary) / "missing.wav"), str(Path(temporary) / "out.wav"))
            self.assertIsNone(engine._model)
