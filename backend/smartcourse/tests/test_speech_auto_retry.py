import json
import tempfile
import unittest
from pathlib import Path
from app.full_pipeline import _run_speech_with_retries
from agents.s3_tts_agent import SpeechCoverageError, TTSAgent


class SpeechAutoRetryTests(unittest.TestCase):
    def test_coverage_failure_preserves_audio_and_invalidates_only_that_page(self):
        class Aligner:
            def get_sentence_timestamps(self, **kwargs):
                return [{'text': 'zzzzzzzzzzzzzzzzzz', 'start': 0, 'end': 1}]
        with tempfile.TemporaryDirectory() as folder:
            wav = Path(folder) / 'page_003.wav'
            wav.write_bytes(b'saved audio')
            wav.with_suffix('.input.json').write_text('{}')
            agent = object.__new__(TTSAgent)
            agent.aligner = Aligner()
            page = {'page_id': 3, 'wav_path': str(wav), 'generation_id': 'attempt-a',
                    'duration': 1, 'script_text': 'A completely different spoken explanation.'}
            with self.assertRaises(SpeechCoverageError):
                agent._align_page(page, 'en')
            failed = Path(folder) / 'failed-checks' / 'page_003' / 'attempt-a'
            self.assertEqual((failed/'page_003.wav').read_bytes(), b'saved audio')
            self.assertFalse(json.loads((failed/'page_003.coverage.json').read_text())['passed'])
            self.assertFalse(wav.with_suffix('.input.json').exists())

    def test_local_speech_retry_is_bounded_and_preserves_other_errors(self):
        calls, events = [], []
        def run():
            calls.append(1)
            if len(calls) < 3:
                raise SpeechCoverageError('page 3')
            return 'done'
        self.assertEqual(_run_speech_with_retries(run, lambda exc, n: events.append(n), SpeechCoverageError), 'done')
        self.assertEqual(events, [1, 2])
        with self.assertRaisesRegex(RuntimeError, 'unrelated'):
            _run_speech_with_retries(lambda: (_ for _ in ()).throw(RuntimeError('unrelated')), lambda *_: None, SpeechCoverageError)


if __name__ == '__main__':
    unittest.main()
