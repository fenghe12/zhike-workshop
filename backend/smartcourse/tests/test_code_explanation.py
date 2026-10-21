import tempfile
import unittest
from pathlib import Path

from app.code_explanation import generate_code_explanation
from app.task_model import validate_creation


class Gateway:
    def __init__(self):
        self.calls = 0

    def respond_json(self, prompt, **_kwargs):
        self.calls += 1
        assert "def add" in prompt
        return {"pages": [
            {"page_id": 1, "title": "函数的输入与返回", "key_points": ["接收两个参数", "返回两数之和"],
             "script_text": "这个函数接收两个参数，并返回它们的和。"},
            {"page_id": 2, "title": "调用与边界", "key_points": ["调用时传入参数", "未指定输入类型"],
             "script_text": "调用时需要提供两个参数。代码没有限制参数的具体类型。"},
        ]}


class CodeExplanationTests(unittest.TestCase):
    def test_custom_code_creation_and_page_generation(self):
        request = validate_creation({
            "name": "求和函数讲解", "mode": "code",
            "inputs": {"codeText": "def add(a, b):\n    return a + b", "codeLanguage": "Python", "totalPages": 2},
            "sourceLanguage": "中文", "targetLanguages": ["中文"],
        })
        self.assertEqual(request["inputs"]["totalPages"], 2)
        with tempfile.TemporaryDirectory() as directory:
            gateway = Gateway()
            pages = generate_code_explanation(request["inputs"]["codeText"], "Python", "zh-CN",
                                              "初学者", 2, gateway, Path(directory) / "pages.json")
            self.assertEqual(len(pages), 2)
            self.assertEqual(pages[0]["script_source"], "generated_from_code")
            generate_code_explanation(request["inputs"]["codeText"], "Python", "zh-CN",
                                      "初学者", 2, gateway, Path(directory) / "pages.json")
            self.assertEqual(gateway.calls, 1)

    def test_mode_requires_exactly_one_source(self):
        base = {"name": "test", "mode": "code", "sourceLanguage": "中文", "targetLanguages": ["中文"]}
        with self.assertRaises(ValueError):
            validate_creation({**base, "inputs": {}})
        with self.assertRaises(ValueError):
            validate_creation({**base, "inputs": {"lessonId": "linear-function", "codeText": "print(1)"}})


if __name__ == "__main__":
    unittest.main()
