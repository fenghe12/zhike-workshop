import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.full_pipeline import FullPipelineRunner, _exact_token_accuracy
from app.server import SmartCourseApplication
from app.translation_policy import validate_policy, meets_thresholds


class TranslationPolicyTests(unittest.TestCase):
    def test_ai_expansion_preserves_the_term_without_ignoring_numbers_or_operators(self):
        source = 'Origin of AI\n1956\nAND'
        for name in ['人工智能', '人工知能', '인공 지능', 'Künstliche Intelligenz',
                     'intelligence artificielle', 'artificial intelligence']:
            self.assertEqual(_exact_token_accuracy(source, name + ' 1956 AND'), 1.0)
        self.assertLess(_exact_token_accuracy(source, '人工智能 1957 AND'), 1.0)
        self.assertLess(_exact_token_accuracy(source, '人工智能 1956'), 1.0)

    def test_invalid_thresholds_are_rejected(self):
        for value in [{"semantic_similarity": float("nan")}, {"terminology_coverage": 1.1},
                      {"maxRetries": 4}, {"maxRetries": True}, {"unknown": 1}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_policy(value)

    def test_model_pass_flag_cannot_override_threshold(self):
        class Gateway:
            calls = 0
            def respond_json(self, *args, **kwargs):
                self.calls += 1
                return {"title": "Topic", "script_text": "Text", "key_points": [], "passed": True,
                        "semantic_similarity": .5, "terminology_coverage": 1,
                        "formula_number_proper_name_accuracy": 1, "contextual_consistency": 1}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = Settings(root/'data', root/'artifacts', 'http://invalid', 'test', '', '127.0.0.1', 0)
            runner = FullPipelineRunner(settings)
            runner.gateway = Gateway()
            _, report = runner._translate_page({"page_id": 1, "title": "Topic", "script_text": "Text"}, "German", {"maxRetries": 0})
            self.assertFalse(report["passed"])
            self.assertEqual(runner.gateway.calls, 1)

    def test_existing_task_keeps_its_saved_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app = SmartCourseApplication(Settings(root/'data', root/'artifacts', 'http://invalid', 'test', '', '127.0.0.1', 0))
            app.store.transact(lambda state: state.update({"translationPolicy": validate_policy({"semantic_similarity": .9})}))
            payload = {"name": "Policy test", "mode": "topic", "inputs": {"topic": "Networks"}, "targetLanguages": ["德语"], "autoExecute": False}
            first = app.add_task(payload, None)
            app.store.transact(lambda state: state.update({"translationPolicy": validate_policy({"semantic_similarity": .95})}))
            second = app.add_task(payload, None)
            self.assertEqual(app.get_task(first["id"])["translationPolicy"]["semantic_similarity"], .9)
            self.assertEqual(second["translationPolicy"]["semantic_similarity"], .95)
