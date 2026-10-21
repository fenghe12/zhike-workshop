import tempfile
import os
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from app.topic_lecture import generate_topic_lecture


class TopicLectureTests(unittest.TestCase):
    def test_oversized_lecture_is_regenerated_not_truncated(self):
        long, short = Mock(), Mock()
        long.json.return_value = {'choices': [{'message': {'content': '长' * 500}}]}
        short.json.return_value = {'choices': [{'message': {'content': '完整保留要点的简短讲稿。'}}]}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'SMARTCOURSE_REMOTE_MEDIA': '0'}), patch(
                'app.topic_lecture.requests.post', side_effect=[long, short]) as call:
            result = generate_topic_lecture([{'page_id': 1, 'title': '主题'}], audience='本科生', minutes=1,
                                             output=Path(directory)/'lecture.json')
            self.assertEqual(call.call_count, 2)
            self.assertEqual(result[0]['script_text'], '完整保留要点的简短讲稿。')

    def test_remote_mode_delegates_page_inputs(self):
        pages = [{'page_id': 1, 'title': '主题'}]
        with patch.dict(os.environ, {'SMARTCOURSE_REMOTE_MEDIA': '1'}), patch(
                'app.remote_topic_lecture.generate_remote_lecture', return_value=pages) as remote:
            self.assertEqual(generate_topic_lecture(pages, audience='本科生', minutes=1,
                                                   output=Path('/tmp/lecture.json')), pages)
            self.assertEqual(remote.call_args.args[0], pages)

    def test_page_order_and_cache(self):
        response = Mock()
        response.json.return_value = {'choices': [{'message': {'content': '本页讲稿。'}}]}
        pages = [{'page_id': 1, 'title': '一'}, {'page_id': 2, 'title': '二'}]
        with tempfile.TemporaryDirectory() as directory, patch('app.topic_lecture.requests.post', return_value=response) as call:
            output = Path(directory) / 'lecture.json'
            result = generate_topic_lecture(pages, audience='本科生', minutes=2, output=output)
            self.assertEqual([p['page_id'] for p in result], [1, 2])
            self.assertEqual(call.call_count, 2)
            self.assertEqual(generate_topic_lecture(pages, audience='本科生', minutes=2, output=output), result)
            self.assertEqual(call.call_count, 2)
