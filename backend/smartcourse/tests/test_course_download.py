import unittest
from app.course_download import validate_source_url


class CourseDownloadTests(unittest.TestCase):
    def test_storage_url_with_signature_is_allowed(self):
        self.assertEqual(validate_source_url('https://storage.example/course.docx?signature=value',
                                            ['storage.example']), 'course.docx')

    def test_unapproved_internal_and_confusing_addresses_are_rejected(self):
        for url in ['http://storage.example/file.pdf', 'https://127.0.0.1/file.pdf',
                    'https://storage.example.evil.test/file.pdf',
                    'https://user@storage.example/file.pdf', 'https://storage.example:8443/file.pdf']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_source_url(url, ['storage.example'])
