import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from app.pdf_validation import pdf_page_count
from app.uploads import save_upload


class PdfValidationTests(unittest.TestCase):
    def test_valid_pdf_upload_keeps_pdf_extension(self):
        with tempfile.TemporaryDirectory() as temporary,patch('app.pdf_validation.pdf_page_count',return_value=10) as validate:
            result=save_upload(Path(temporary),'course.pdf','ppt',b'PDF fixture')
            self.assertTrue(result['path'].endswith('/source.pdf'))
            validate.assert_called_once_with(content=b'PDF fixture')

    def test_invalid_pdf_does_not_create_upload_directory(self):
        with tempfile.TemporaryDirectory() as temporary,patch('app.pdf_validation.pdf_page_count',side_effect=ValueError('PDF 损坏')):
            root=Path(temporary)
            with self.assertRaises(ValueError):save_upload(root,'bad.pdf','ppt',b'invalid')
            self.assertFalse((root/'uploads').exists())

    def test_encrypted_empty_and_corrupt_pdf_rejected(self):
        for output,code in ((b'Pages: 2\nEncrypted: yes\n',0),(b'Pages: 0\n',0),(b'',1)):
            with patch('app.pdf_validation.shutil.which',return_value='/pdfinfo'),patch('app.pdf_validation.subprocess.run',return_value=SimpleNamespace(stdout=output,returncode=code)),self.assertRaises(ValueError):
                pdf_page_count(content=b'fixture')
