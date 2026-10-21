import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.remote_media import media_service_status


class RemoteMediaStatusTests(unittest.TestCase):
    def test_local_media_mode_is_ready(self):
        with patch.dict('os.environ', {'SMARTCOURSE_REMOTE_MEDIA': '0'}, clear=False):
            self.assertEqual(media_service_status(), 'LOCAL')

    def test_remote_state_is_reported(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            state.write_text(json.dumps({'status': 'STOPPED'}))
            with patch.dict('os.environ', {
                'SMARTCOURSE_REMOTE_MEDIA': '1',
                'SMARTCOURSE_REMOTE_STATE': str(state),
            }, clear=False):
                self.assertEqual(media_service_status(), 'STOPPED')

    def test_invalid_remote_state_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / 'state.json'
            state.write_text('invalid')
            with patch.dict('os.environ', {
                'SMARTCOURSE_REMOTE_MEDIA': '1',
                'SMARTCOURSE_REMOTE_STATE': str(state),
            }, clear=False):
                self.assertEqual(media_service_status(), 'UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
