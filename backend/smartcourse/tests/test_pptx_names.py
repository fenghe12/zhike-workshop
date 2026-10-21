import unittest
from app.pptx_names import localized_person_names


class PptxNameTests(unittest.TestCase):
    def test_confirmed_chinese_namee(self):
        self.assertEqual(localized_person_names(['Tonghua Su'],'Simplified Chinese'),{'Tonghua Su':'苏统华'})

    def test_other_language_uses_official_latin_spelling(self):
        self.assertEqual(localized_person_names(['Tonghua Su'],'Russian'),{'Tonghua Su':'Tonghua Su'})
