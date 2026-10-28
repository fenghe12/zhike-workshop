import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.full_pipeline import FullPipelineRunner, _exact_token_accuracy, _translation_warning
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

    def test_equivalent_japanese_amounts_are_not_rejected(self):
        source = 'US AI salaries 1.5 million RMB and CAPEX $1.3 billion'
        self.assertEqual(_exact_token_accuracy(source, '米国 AI 給与 150万 人民元 CAPEX 13億ドル'), 1.0)
        self.assertLess(_exact_token_accuracy(source, '米国 AI 給与 150万 人民元 CAPEX 12億ドル'), 1.0)

    def test_failed_page_retries_three_times_and_keeps_warning(self):
        class Gateway:
            calls = 0
            def respond_json(self, *args, **kwargs):
                self.calls += 1
                return {"script_text": "Übersetzter Text", "passed": False,
                        "semantic_similarity": .5, "terminology_coverage": 1,
                        "formula_number_proper_name_accuracy": 1, "contextual_consistency": 1}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = FullPipelineRunner(Settings(root/'data', root/'artifacts', 'http://invalid', 'test', '', '127.0.0.1', 0))
            runner.gateway = Gateway()
            result, report = runner._translate_page({"page_id": 7, "script_text": "Some text"}, "German")
            self.assertEqual(runner.gateway.calls, 4)
            self.assertEqual(result['script_text'], 'Übersetzter Text')
            self.assertFalse(report['passed'])
            self.assertIn('7', _translation_warning([report]))

    def test_wrong_language_and_invalid_json_are_retried(self):
        from app.gateway import GatewayError
        class Gateway:
            calls = 0
            def respond_json(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise GatewayError('网关返回的 JSON 不完整')
                text = ('现在我们开始进入人工智能起源与概述的章节。我们希望智能机器做什么？'
                        '我们可能期望它能沟通、从经验中学习、识别模式或解决问题。' if self.calls == 2 else
                        'これから人工知能の起源と概要について学びます。人間が知能を持つ機械に何を期待するのか、'
                        '経験から学ぶことや問題を解決することについて考えていきましょう。')
                return {'script_text': text, 'passed': True, 'semantic_similarity': 1,
                        'terminology_coverage': 1, 'formula_number_proper_name_accuracy': 1,
                        'contextual_consistency': 1}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = FullPipelineRunner(Settings(root/'data', root/'artifacts', 'http://invalid', 'test', '', '127.0.0.1', 0))
            runner.gateway = Gateway()
            result, report = runner._translate_page({'page_id':3, 'script_text':'This is a lecture about artificial intelligence.'}, 'Japanese')
            self.assertEqual(runner.gateway.calls, 3)
            self.assertTrue(report['passed'])
            self.assertEqual(report['languageCheck']['status'], 'match')
            self.assertIn('これから', result['script_text'])

    def test_short_japanese_text_can_be_identified_without_calling_it_chinese(self):
        from app.language_validation import check_target_language
        self.assertEqual(check_target_language('このスライドのタイトルです。', 'Japanese')['status'], 'match')
        self.assertEqual(check_target_language('机器学习', 'Japanese')['status'], 'insufficient_text')

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
            self.assertEqual(runner.gateway.calls, 2)

    def test_script_translation_does_not_receive_slide_footer(self):
        import json

        class Gateway:
            def __init__(self):
                self.pages = []

            def respond_json(self, prompt, **kwargs):
                page = json.loads(prompt.split("Source page:\n", 1)[1].split("\nRequired quality thresholds:", 1)[0])
                self.pages.append(page)
                return {"title": "Topic" if page["title"] else "",
                        "key_points": ["Course materials, page 1"] if page["key_points"] else [],
                        "script_text": "This is the narration." if page["script_text"] else "",
                        "passed": True, "semantic_similarity": 1, "terminology_coverage": 1,
                        "formula_number_proper_name_accuracy": 1, "contextual_consistency": 1}

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = FullPipelineRunner(Settings(root/'data', root/'artifacts', 'http://invalid', 'test', '', '127.0.0.1', 0))
            runner.gateway = Gateway()
            page = {"page_id": 1, "title": "主题", "key_points": ["课程资料 · 第 1 页"],
                    "script_text": "这是讲稿。", "layout": {"footer": "课程资料 · 第 1 页"}}
            result, report = runner._translate_page(page, "English", {"maxRetries": 0})
            self.assertNotIn("课程资料", json.dumps(runner.gateway.pages[1], ensure_ascii=False))
            self.assertEqual(result["script_text"], "This is the narration.")
            self.assertEqual(result["key_points"], ["Course materials, page 1"])
            self.assertTrue(report["passed"])

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
