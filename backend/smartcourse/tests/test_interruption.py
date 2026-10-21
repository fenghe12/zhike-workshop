import unittest
from app.interruption import prepare_interruption, generate_interruption_answer, load_interruption_context
import tempfile
from unittest.mock import Mock


class InterruptionTests(unittest.TestCase):
    def test_context_cannot_read_other_task_files(self):
        with tempfile.TemporaryDirectory() as directory:
            task = {'id': 'one', 'targetLanguages': ['韩语'], 'outputs': {'s1': {
                'courseStructure': '/artifacts/tasks/two/s1/course_structure.json'}}}
            with self.assertRaisesRegex(ValueError, '不属于当前任务'):
                load_interruption_context(task, {'targetLanguage': 'ko-KR'}, directory)

    def test_answer_uses_only_actual_course_pages(self):
        gateway = Mock()
        gateway.respond_json.return_value = {'answer': '가중치를 곱한 값을 더합니다.', 'sourcePages': [2],
                                             'needsClarification': False, 'slideOutline': ['가중 합']}
        self.assertEqual(generate_interruption_answer(self.prepare(), gateway)['sourcePages'], [2])
        gateway.respond_json.return_value['sourcePages'] = [99]
        with self.assertRaises(ValueError):
            generate_interruption_answer(self.prepare(), gateway)

    def prepare(self, **changes):
        payload = {'question': '为什么？', 'currentPage': 2, 'currentTime': 83.5, 'targetLanguage': 'ko-KR'}
        payload.update(changes)
        return prepare_interruption(payload, {'pages': [{'page_id': 2, 'title': '加权求和', 'script_text': '用户讲稿'}]},
                                    {'pages': [{'page_id': 2, 'start_time': 60, 'end_time': 120}]}, ['韩语'])

    def test_preserves_resume_position_and_actual_script(self):
        result = self.prepare()
        self.assertEqual(result['resumePosition']['currentTime'], 83.5)
        self.assertEqual(result['currentPage']['script_text'], '用户讲稿')

    def test_invalid_positions_and_language_are_rejected(self):
        for changes in [{'currentPage': True}, {'currentPage': 3}, {'currentTime': float('nan')},
                        {'currentTime': -1}, {'currentTime': 5}, {'targetLanguage': 'ja-JP'}, {'question': ''}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.prepare(**changes)
