import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape
from app.lecture_input import read_page_scripts


class LectureInputTests(unittest.TestCase):
    def read(self, paragraphs, count):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'script.docx'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('word/document.xml',
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    + ''.join(f'<w:p><w:r><w:t>{escape(p)}</w:t></w:r></w:p>' for p in paragraphs)
                    + '</w:document>')
            return read_page_scripts(path, count)

    def test_preserves_user_words_and_page_boundaries(self):
        self.assertEqual(self.read(['第 1 页', 'First sentence.', 'Second sentence.', '第 2 页', 'Next page.'], 2),
                         ['First sentence.\nSecond sentence.', 'Next page.'])

    def test_one_paragraph_per_page(self):
        self.assertEqual(self.read(['첫 페이지.', '다음 페이지.'], 2), ['첫 페이지.', '다음 페이지.'])

    def test_missing_or_duplicate_pages_are_rejected(self):
        for paragraphs in [['第 1 页', 'Text'], ['第 1 页', 'Text', '第 1 页', 'Other']]:
            with self.assertRaises(ValueError): self.read(paragraphs, 2)

    def test_empty_page_is_rejected(self):
        with self.assertRaises(ValueError): self.read(['第 1 页', 'Text', '第 2 页'], 2)

    def test_unassigned_opening_is_not_silently_discarded(self):
        with self.assertRaisesRegex(ValueError, '未分配文字'):
            self.read(['Opening narration', '第 1 页', 'Page narration'], 1)

    def test_page_marker_with_multiline_body(self):
        self.assertEqual(self.read(['第 1 页\nFirst sentence.\nSecond sentence.'], 1),
                         ['First sentence.\nSecond sentence.'])

    def test_word_breaks_and_tabs_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'script.docx'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('word/document.xml',
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    '<w:p><w:r><w:t>第1页</w:t><w:br/><w:t>First</w:t><w:tab/>'
                    '<w:t>part</w:t><w:br/><w:t>Second</w:t></w:r></w:p></w:document>')
            self.assertEqual(read_page_scripts(path, 1), ['First\tpart\nSecond'])

    def test_repeated_placeholder_lecture_is_rejected(self):
        paragraphs = []
        for index in range(1, 5):
            paragraphs.extend([f'第 {index} 页', f'讲稿：神经网络基础第{index}页',
                               f'本页讲解神经网络基础的第{index}页内容，包含定义、公式和教学示例。'])
        with self.assertRaisesRegex(ValueError, '占位内容'):
            self.read(paragraphs, 4)
