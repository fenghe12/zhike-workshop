import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.pdf_stage import prepare_pdf_stage


class PdfStageTests(unittest.TestCase):
    def test_original_documents_and_scripts_retained_without_pptx(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            pdf=root/'input.pdf';pdf.write_bytes(b'original PDF')
            script=root/'input.docx';script.write_bytes(b'original DOCX')
            output=root/'s1'
            structure={'total_pages':1,'pages':[{'page_id':1,'title':'课件','script_text':'完整原稿。'}]}
            with patch('app.pdf_stage.pdf_pipeline_structure',return_value=structure),patch('app.pdf_stage.render_pdf_pages',return_value=['page.png']):
                result=prepare_pdf_stage(pdf,script,output,'one','zh-CN','Chinese')
            self.assertEqual((output/'source.pdf').read_bytes(),pdf.read_bytes())
            self.assertEqual((output/'source_lecture.docx').read_bytes(),script.read_bytes())
            self.assertFalse((output/'generated.pptx').exists())
            self.assertEqual(result['pageCount'],1)
            self.assertEqual(json.loads((output/'course_structure.json').read_text())['pages'][0]['script_text'],'完整原稿。')
