import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.narrated_document import prepare_narrated_document


class NarratedDocumentTests(unittest.TestCase):
    def test_pdf_preserved_without_powerpoint_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'s2';source.mkdir()
            original=source/'translated.pdf';original.write_bytes(b'original PDF content')
            with patch('app.pptx_notes.write_speaker_notes') as notes,patch('app.pptx_fonts.apply_language_font') as fonts:
                result=prepare_narrated_document(source,root/'s3',{'input_mode':'existing_pdf','pages':[]},'ko-KR')
            self.assertEqual(result.suffix,'.pdf')
            self.assertEqual(result.read_bytes(),original.read_bytes())
            notes.assert_not_called();fonts.assert_not_called()
