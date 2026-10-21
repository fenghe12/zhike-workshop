import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.full_pipeline import FullPipelineRunner
from app.server import SmartCourseApplication
from app.translation_policy import validate_policy, meets_thresholds


class TranslationPolicyTests(unittest.TestCase):
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
