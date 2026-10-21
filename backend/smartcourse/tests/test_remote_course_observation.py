import subprocess
import unittest
from unittest.mock import patch

from app.remote_deeppresenter import wait_remote_result


class RemoteObservationTests(unittest.TestCase):
    @patch('app.remote_deeppresenter.time.sleep')
    @patch('app.remote_deeppresenter.subprocess.run')
    def test_connection_failure_does_not_resubmit(self, run, sleep):
        run.side_effect = [subprocess.CompletedProcess([], 255, '', ''),
                           subprocess.CompletedProcess([], 0, '{"status":"running"}', ''),
                           subprocess.CompletedProcess([], 0, '{"status":"completed"}', '')]
        self.assertEqual(wait_remote_result(['ssh', 'host'], '/job')['status'], 'completed')
        self.assertTrue(all(call.args[0][-1] == 'cat /job/result.json' for call in run.call_args_list))

    @patch('app.remote_deeppresenter.subprocess.run')
    def test_actual_failure_is_reported(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, '{"status":"failed","error":"生成失败"}', '')
        with self.assertRaisesRegex(RuntimeError, '生成失败'):
            wait_remote_result(['ssh', 'host'], '/job')

    @patch('app.remote_deeppresenter.time.sleep')
    @patch('app.remote_deeppresenter.subprocess.run')
    def test_observation_timeout_is_retried(self, run, sleep):
        run.side_effect = [subprocess.TimeoutExpired('ssh', 30),
                           subprocess.CompletedProcess([], 0, '{"status":"completed"}', '')]
        self.assertEqual(wait_remote_result(['ssh', 'host'], '/job')['status'], 'completed')


if __name__ == '__main__':
    unittest.main()
