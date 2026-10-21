import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.page_video_delivery import export_page_videos


class PageVideoValidationTests(unittest.TestCase):
    @patch('app.page_video_delivery.shutil.which', return_value='/tools/ffmpeg')
    @patch('app.page_video_delivery.subprocess.run')
    def test_invalid_timeline_never_starts_encoding(self, run, which):
        invalid = [[], [{'page_id': 1, 'start': 0, 'end': float('nan')}],
                   [{'page_id': True, 'start': 0, 'end': 1}],
                   [{'page_id': 1, 'start': 0, 'end': 1}, {'page_id': 1, 'start': 1, 'end': 2}],
                   [{'page_id': 1, 'start': 1, 'end': 2}],
                   [{'page_id': 1, 'start': 0, 'end': 2}, {'page_id': 2, 'start': 1, 'end': 3}]]
        with tempfile.TemporaryDirectory() as directory:
            for pages in invalid:
                with self.subTest(pages=pages), self.assertRaises(ValueError):
                    export_page_videos('video.mp4', {'pages': pages}, Path(directory) / 'output')
        run.assert_not_called()
