import tempfile
import unittest
from pathlib import Path
from app.upload_lecture import generate_upload_lecture


class UploadLectureSourceTests(unittest.TestCase):
    def test_auto_narration_passes_slide_image_to_model(self):
        class Gateway:
            def respond_json(self, prompt, **kwargs):
                self.images = kwargs.get('image_paths')
                return {'script_text': 'The slide presents two examples of artificial intelligence in science.'}
        gateway = Gateway()
        with tempfile.TemporaryDirectory() as folder:
            image = Path(folder) / 'slide.png'
            image.write_bytes(b'example image')
            pages = {'pages':[{'page_id':1, 'title':'Topic', 'key_points':['Examples']}]}
            generate_upload_lecture(pages, gateway, 'en-US', Path(folder)/'generated', slide_images=[image])
            self.assertEqual(gateway.images, [image])

    def test_invalid_model_response_is_retried_for_the_same_page(self):
        from app.gateway import GatewayError
        class Gateway:
            calls = 0
            def respond_json(self, *args, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise GatewayError('网关文本中没有 JSON 对象')
                return {'script_text': 'This lesson explains the teaching content clearly.'}
        gateway = Gateway()
        with tempfile.TemporaryDirectory() as folder:
            result = generate_upload_lecture({'pages':[{'page_id':1, 'title':'Topic', 'key_points':['Content']}]}, gateway, 'en-US', Path(folder))
        self.assertEqual(gateway.calls, 2)
        self.assertEqual(result[0]['script_source'], 'generated_from_slide')

    def test_generation_uses_visible_slide_content_even_when_notes_exist(self):
        class Gateway:
            calls = 0
            def respond_json(self, prompt, **kwargs):
                self.calls += 1
                self.prompt = prompt
                return {'script_text': 'This lesson explains the visible topic and its main ideas.'}
        page = {'page_id': 1, 'title': 'Visible topic', 'key_points': ['Main ideas'],
                'script_source': 'speaker_notes', 'script_text': 'Do not use this old note.'}
        gateway = Gateway()
        with tempfile.TemporaryDirectory() as folder:
            result = generate_upload_lecture({'pages': [page]}, gateway, 'en-US', Path(folder))
        self.assertEqual(gateway.calls, 1)
        self.assertEqual(result[0]['script_source'], 'generated_from_slide')
        self.assertNotIn('old note', gateway.prompt)
        self.assertIn('visible topic', result[0]['script_text'])


if __name__ == '__main__':
    unittest.main()
