import unittest
from app.narration import validate_spoken_text


class SpokenTextTests(unittest.TestCase):
    def test_plain_korean_is_accepted(self):
        text = '입력과 가중치를 곱한 뒤 편향을 더합니다.'
        self.assertEqual(validate_spoken_text(text), text)

    def test_formatting_and_formula_source_are_rejected(self):
        for text in ['**강조**', '$x_i$', r'\sum x', '```json', '<tool_call>', 'x_i', 'net = 2', 'net ≥ 0', '']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                validate_spoken_text(text)
