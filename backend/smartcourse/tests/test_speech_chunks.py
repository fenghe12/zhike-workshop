import unittest
from agents.cosyvoice_engine import prepare_spoken_text, speech_chunks
from app.speech_coverage import coverage_report


class SpeechChunkTests(unittest.TestCase):
    def test_long_paragraph_keeps_every_word(self):
        source = ' '.join('term'+str(i) for i in range(100)) + '; final definition.'
        chunks = speech_chunks(source, 100)
        self.assertTrue(all(len(chunk) <= 100 for chunk in chunks))
        self.assertEqual(''.join(''.join(chunks).split()), ''.join(source.split()))
        self.assertTrue(chunks[-1].endswith('final definition.'))

    def test_formula_operators_are_localized_without_changing_word_hyphens(self):
        text = prepare_spoken_text('M-P-Modell\n𝑨=(TP+TN)/(TP+TN+FP+FN)', 'de')
        self.assertIn('M-P-Modell', text)
        self.assertIn('gleich', text)
        self.assertIn('geteilt durch', text)
        self.assertNotIn('𝑨', text)

    def test_missing_final_explanation_fails_coverage(self):
        source = 'Beginning. ' + 'Distinct technical explanation with variables and definitions. ' * 5
        self.assertFalse(coverage_report(source, [{'text': 'Beginning.'}])['passed'])
        self.assertTrue(coverage_report(source, [{'text': source}])['passed'])


if __name__ == '__main__':
    unittest.main()
