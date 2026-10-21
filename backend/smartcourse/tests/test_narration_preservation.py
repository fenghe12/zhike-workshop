import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from app.narration import prepare_narration


class NarrationPreservationTests(unittest.TestCase):
    def test_uploaded_script_is_not_rewritten(self):
        structure = {'pages': [{'page_id': 1, 'script_text': '첫 문장.\n두 번째 문장.',
                                'script_source': 'translation_agent'}]}
        gateway = Mock()
        with tempfile.TemporaryDirectory() as directory:
            result = prepare_narration(structure, gateway, Path(directory) / 'script.json',
                                       preserve_script=True)
            self.assertEqual(json.loads(result.read_text()), structure)
        gateway.respond_json.assert_not_called()

    def test_missing_script_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for pages in [[], [{'page_id': 1}], [{'page_id': 1, 'script_text': ' '}]]:
                with self.assertRaises(ValueError):
                    prepare_narration({'pages': pages}, Mock(), Path(directory) / 'script.json',
                                      preserve_script=True)
