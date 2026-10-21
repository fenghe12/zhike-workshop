import unittest
from app.task_recovery import recover_exited_workers


class RecoveryTests(unittest.TestCase):
    def test_interruption_recovery_preserves_answer_and_position(self):
        record = {'status': 'running', 'workerHost': 'test-host', 'workerPid': 123,
                  'answer': '已有回答', 'resumePosition': {'currentTime': 80}}
        recover_exited_workers({'interruptions': {'one': record}}, alive=lambda _: False, host='test-host')
        self.assertEqual(record['status'], 'failed')
        self.assertEqual(record['answer'], '已有回答')
        self.assertEqual(record['resumePosition']['currentTime'], 80)

    def test_dead_worker_preserves_completed_outputs(self):
        task = {'status': 'processing', 'workerHost': 'test-host', 'workerPid': 123,
                'currentStage': 2, 'outputs': {'s1': {'pptx': 'saved.pptx'}},
                'stages': [{'status': 'completed'}, {'status': 'running'}]}
        recover_exited_workers({'tasks': {'one': task}}, alive=lambda _: False, host='test-host')
        self.assertEqual(task['status'], 'failed')
        self.assertIn('s1', task['outputs'])
        self.assertEqual(task['stages'][0]['status'], 'completed')

    def test_live_or_other_host_worker_is_not_changed(self):
        for host, live in [('test-host', True), ('other-host', False)]:
            task = {'status': 'processing', 'workerHost': host, 'workerPid': 123}
            recover_exited_workers({'tasks': {'one': task}}, alive=lambda _: live, host='test-host')
            self.assertEqual(task['status'], 'processing')
