import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.store import JsonStore
from app.interruption_jobs import submit_interruption, execute_interruption, public_interruption


class InterruptionJobTests(unittest.TestCase):
    @patch('app.interruption_jobs.generate_interruption_answer')
    def test_retry_continues_existing_child_stage(self, answer):
        record = {'generationTaskId': 'child', 'answer': '已审核回答', 'needsSlides': True,
                  'slideOutline': ['主题'], 'sourcePages': [2], 'needsClarification': False}
        self.application.store.transact(lambda data: data.update(interruptions={'answer-1': record}))
        self.application.get_task = Mock(return_value={'id': 'child', 'createdBy': 'owner',
            'inputs': {'interruptionParent': 'course-1'}, 'status': 'failed', 'currentStage': 3})
        self.application.add_task = Mock()
        self.application.execute_task = Mock(return_value={'status': 'completed', 'outputs': {'s5': {'languages': {
            'ko-KR': {'video': '/artifacts/tasks/child/video.mp4', 'coursePptx': '/artifacts/tasks/child/course.pptx'}}}}})
        execute_interruption(self.application, {'id': 'course-1', 'createdBy': 'owner'}, self.context, 'answer-1')
        answer.assert_not_called()
        self.application.add_task.assert_not_called()
        self.application.execute_task.assert_called_once_with('child', start_stage=3, asynchronous=False)

    def test_pending_slide_job_does_not_publish_completion_claim(self):
        result = public_interruption({'status': 'running', 'needsSlides': True,
                                      'answer': '课件已经生成', 'videoUrl': None})
        self.assertIsNone(result['answer'])
        self.assertIn('正在生成', result['message'])
        completed = public_interruption({'status': 'completed', 'needsSlides': True, 'answer': '课程回答'})
        self.assertEqual(completed['answer'], '课程回答')

    @patch('app.interruption_jobs.generate_interruption_answer')
    def test_slide_answer_reuses_pipeline_and_parent_references(self, answer):
        answer.return_value = {'answer': '回答正文', 'needsSlides': True, 'slideOutline': ['推导'],
                               'sourcePages': [2], 'needsClarification': False}
        self.application.add_task = Mock(return_value={'id': 'child'})
        self.application.execute_task = Mock(return_value={'status': 'completed', 'outputs': {'s5': {'languages': {
            'ko-KR': {'video': '/artifacts/tasks/child/video.mp4', 'coursePptx': '/artifacts/tasks/child/course.pptx'}}}}})
        self.application.store.transact(lambda data: data.update(interruptions={'answer-1': {}}))
        assets = {'referenceAudio': {'path': '/artifacts/voice.wav'}, 'referenceImage': {'path': '/artifacts/photo.png'}}
        task = {'id': 'course-1', 'createdBy': 'owner', 'assets': assets}
        execute_interruption(self.application, task, self.context, 'answer-1')
        record = self.application.store.snapshot()['interruptions']['answer-1']
        self.assertEqual(record['status'], 'completed')
        self.assertEqual(record['pptUrl'], '/artifacts/tasks/child/course.pptx')
        self.assertEqual(self.application.add_task.call_args.kwargs['validated_assets'], assets)
        self.application.execute_task.assert_called_once_with('child', asynchronous=False)

    def test_public_response_omits_internal_execution_fields(self):
        result = public_interruption({'id': 'one', 'status': 'running', 'workerPid': 123,
                                      'workerHost': 'private-host', 'secret': 'private'})
        self.assertEqual(result, {'id': 'one', 'status': 'running'})

    def setUp(self):
        presentation = patch('pptx.Presentation')
        presentation.start().return_value.slides = []
        self.addCleanup(presentation.stop)
        review = patch('app.course_content_review.review_course_content', return_value={'passed':True,'checks':[]})
        review.start()
        self.addCleanup(review.stop)
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        self.application = SimpleNamespace(settings=SimpleNamespace(artifact_root=root),
                                           store=JsonStore(root / 'state.json'),
                                           pipeline_runner=SimpleNamespace(gateway=Mock(), _resolve_asset=lambda value:value))
        self.context = {'question': '为什么？', 'targetLanguage': 'ko-KR',
                        'resumePosition': {'currentPage': 2, 'currentTime': 80}}

    @patch('app.interruption_jobs.threading.Thread')
    @patch('app.interruption_jobs.load_interruption_context')
    def test_submission_is_persisted_before_worker_start(self, context, thread):
        context.return_value = self.context
        record = submit_interruption(self.application, {'id': 'course-1'}, {})
        stored = self.application.store.snapshot()['interruptions'][record['id']]
        self.assertEqual(stored['status'], 'queued')
        self.assertEqual(stored['resumePosition']['currentTime'], 80)
        self.assertIsNone(stored['videoUrl'])
        thread.return_value.start.assert_called_once()

    @patch('app.interruption_jobs.logging.exception')
    @patch('app.interruption_jobs.generate_interruption_answer', side_effect=RuntimeError('internal detail'))
    def test_failure_keeps_position_and_does_not_expose_exception(self, answer, log):
        self.application.store.transact(lambda data: data.update(interruptions={'answer-1': {
            'resumePosition': self.context['resumePosition'], 'videoUrl': None}}))
        execute_interruption(self.application, {'id': 'course-1'}, self.context, 'answer-1')
        record = self.application.store.snapshot()['interruptions']['answer-1']
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['resumePosition']['currentTime'], 80)
        self.assertNotIn('internal detail', record['message'])
        self.assertIsNone(record['videoUrl'])
        log.assert_called_once()

    @patch('app.interruption_jobs.threading.Thread')
    @patch('app.interruption_jobs.load_interruption_context')
    def test_repeated_pending_question_reuses_job(self, context, thread):
        context.return_value = self.context
        first = submit_interruption(self.application, {'id': 'course-1'}, {})
        second = submit_interruption(self.application, {'id': 'course-1'}, {})
        self.assertEqual(first['id'], second['id'])
        thread.return_value.start.assert_called_once()
        context.return_value = {**self.context, 'question': '另外的问题'}
        with self.assertRaisesRegex(ValueError, '正在处理'):
            submit_interruption(self.application, {'id': 'course-1'}, {})
        self.assertEqual(len(self.application.store.snapshot()['interruptions']), 1)
