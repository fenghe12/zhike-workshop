import unittest
from app.pdf_translation import text_is_mathematical, validate_pdf_translations


class PdfTranslationTests(unittest.TestCase):
    def test_comparison_direction_cannot_change(self):
        with self.assertRaisesRegex(ValueError, '比较符号'):
            validate_pdf_translations([{'sourceText': '条件 9 > 5'}], {'translations': ['조건 9 < 5']})

    def test_nonzero_word_and_digit_expression_are_equivalent(self):
        self.assertEqual(validate_pdf_translations([{'sourceText': '非零输出'}],
                         {'translations': ['0이 아닌 출력']}), ['0이 아닌 출력'])
        with self.assertRaisesRegex(ValueError, '数字'):
            validate_pdf_translations([{'sourceText': '非零输出'}], {'translations': ['100이 아닌 출력']})
        with self.assertRaisesRegex(ValueError, '数字'):
            validate_pdf_translations([{'sourceText': '非零输出'}], {'translations': ['0인 출력']})

    def test_ids_restore_order_and_reject_merged_fragments(self):
        items = [{'sourceText': '标题'}, {'sourceText': '正文'}]
        self.assertEqual(validate_pdf_translations(items, {'translations': {'1': 'Body', '0': 'Title'}}), ['Title','Body'])
        with self.assertRaisesRegex(ValueError, '编号'):
            validate_pdf_translations(items, {'translations': {'0': 'Title and body'}})

    def test_subscript_digits_keep_the_same_numeric_values(self):
        self.assertEqual(validate_pdf_translations([{'sourceText': 'w1=2'}],
                         {'translations': ['w₁=2']}), ['w₁=2'])

    def test_math_fragments_are_preserved(self):
        self.assertTrue(text_is_mathematical('x = 2', 'Arial'))
        self.assertTrue(text_is_mathematical('x', 'CambriaMath'))
        self.assertFalse(text_is_mathematical('Input value is 2', 'Arial'))

    def test_numbers_cannot_be_changed(self):
        with self.assertRaisesRegex(ValueError, '数字'):
            validate_pdf_translations([{'sourceText': '值为 2.5'}], {'translations': ['Value is 2.0']})
        self.assertEqual(validate_pdf_translations([{'sourceText': '值为 2.5'}],
                         {'translations': ['Value is 2.5']}), ['Value is 2.5'])
