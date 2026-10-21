import io
import tempfile
import unittest
import wave
import zipfile
from pathlib import Path

from app.uploads import save_upload


def audio(samples):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(samples)
    return buffer.getvalue()


class UploadTests(unittest.TestCase):
    def test_invalid_docx_body_is_rejected_before_storage(self):
        with tempfile.TemporaryDirectory() as directory:
            for body in ['<broken', '<document/>', '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>']:
                data = io.BytesIO()
                with zipfile.ZipFile(data, 'w') as archive:
                    archive.writestr('[Content_Types].xml', '<Types/>')
                    archive.writestr('word/document.xml', body)
                with self.assertRaises(ValueError):
                    save_upload(Path(directory), 'lecture.docx', 'script', data.getvalue())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_same_name_preserves_both_contents(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_content = audio(b"\x00\x00" * 160)
            second_content = audio(b"\x01\x00" * 320)
            first = save_upload(root, "参考.wav", "audio", first_content)
            second = save_upload(root, "参考.wav", "audio", second_content)
            self.assertNotEqual(first["path"], second["path"])
            for asset, content in ((first, first_content), (second, second_content)):
                self.assertEqual((root / asset["path"].removeprefix("/artifacts/")).read_bytes(), content)

    def test_invalid_uploads_create_no_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = [
                ("../x.wav", "audio", audio(b"\0\0")),
                ("x.wav", "../audio", audio(b"\0\0")),
                ("", "audio", b"data"),
                ("x.wav", "audio", b""),
                ("x.png", "audio", b"invalid"),
                ("x.png", "image", b"invalid"),
                ("x.wav", "audio", b"invalid"),
                ("x.pptx", "ppt", b"invalid"),
            ]
            for case in cases:
                with self.subTest(case=case[:2]), self.assertRaises(ValueError):
                    save_upload(root, *case)
            self.assertEqual(list(root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
