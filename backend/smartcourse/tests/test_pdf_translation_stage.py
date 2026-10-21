import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from app.pdf_translation_stage import translate_pdf_stage


class PdfTranslationStageTests(unittest.TestCase):
    def test_failed_narration_stops_before_pdf_translation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            source={'source_pdf':'unused.pdf','pages':[{'page_id':1,'script_text':'原稿'}]}
            translate=Mock(return_value=({'page_id':1,'script_text':'Rejected'},{'passed':False}))
            with patch('app.pdf_translation_stage.translate_pdf_in_worker') as worker,self.assertRaisesRegex(ValueError,'未通过检查'):
                translate_pdf_stage(source,root,'ko-KR','Korean','zh-CN',SimpleNamespace(gateway_model='test'),translate,'font')
            worker.assert_not_called()
            self.assertFalse((root/'translated_structure.json').exists())

    def test_same_language_retains_pdf_and_exact_scripts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);pdf=root/'source.pdf';pdf.write_bytes(b'original PDF bytes')
            source={'source_pdf':str(pdf),'input_mode':'existing_pdf','pages':[{'page_id':1,'title':'课程','script_text':'逐页原稿。','key_points':['内容'],'formulas':[]}]}
            translate=Mock(side_effect=AssertionError('Identity must not generate text'))
            with patch('app.pdf_translation_stage.render_pdf_pages',return_value=['page.png']):
                result=translate_pdf_stage(source,root/'s2','ko-KR','Korean','ko-KR',SimpleNamespace(gateway_model='test'),translate,'unused-font')
            self.assertTrue(result['passed'])
            self.assertEqual(Path(result['translatedPdf']).read_bytes(),pdf.read_bytes())
            self.assertIn('逐页原稿。',Path(result['lectureScript']).read_text())
            translate.assert_not_called()
