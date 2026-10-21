import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from app.pdf_render import render_pdf_pages
from agents.s5_compose_agent import can_reuse_ppt_images
from agents.s5_compose_agent import ComposeAgent
from agents.s5_video_composer import convert_pptx_to_images


class PdfRenderTests(unittest.TestCase):
    def test_pdf_composition_uses_original_pdf_renderer(self):
        with patch('app.pdf_render.render_pdf_pages',return_value=['slide_001.png']) as render:
            result=convert_pptx_to_images('/course.PDF','/pages')
        self.assertEqual(result,['slide_001.png'])
        render.assert_called_once_with('/course.PDF','/pages')

    def test_missing_poppler_uses_pymupdf(self):
        import pymupdf
        with tempfile.TemporaryDirectory() as temporary:
            source=Path(temporary)/'course.pdf'
            document=pymupdf.open()
            document.new_page()
            document.save(source)
            document.close()
            with patch('app.pdf_render.shutil.which',return_value=None):
                outputs=render_pdf_pages(source,Path(temporary)/'pages')
            self.assertEqual(len(outputs),1)
            self.assertTrue(Path(outputs[0]).is_file())

    def test_stale_ppt_images_are_not_reused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / 'course.pptx'
            source.write_bytes(b'pptx')
            images = [root / 'slide_001.png']
            images[0].write_bytes(b'png')
            import os
            os.utime(source, ns=(2_000_000_000, 2_000_000_000))
            os.utime(images[0], ns=(2_100_000_000, 2_100_000_000))
            self.assertTrue(can_reuse_ppt_images(source, images, 1))
            os.utime(source, ns=(3_000_000_000, 3_000_000_000))
            self.assertFalse(can_reuse_ppt_images(source, images, 1))

    def test_force_refresh_removes_old_png_before_render(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            old = directory / 'slide_001.png'
            old.write_bytes(b'old')
            with patch('app.pptx_render.render_pptx', return_value=['fresh.png']) as render:
                result = convert_pptx_to_images('/course.pptx', str(directory), force_refresh=True)
            self.assertFalse(old.exists())
            self.assertEqual(result, ['fresh.png'])
            render.assert_called_once_with('/course.pptx', str(directory))

    def test_caption_area_stays_left_of_bottom_right_avatar(self):
        bbox = {
            1: {
                'x_px': 1403,
                'y_px': 562,
                'size_px': 512,
                'img_w': 1920,
                'img_h': 1079,
            }
        }
        left, right = ComposeAgent._subtitle_horizontal_bounds(1920, 1080, bbox)
        self.assertGreaterEqual(left, 0)
        self.assertLessEqual(right, 1403)
