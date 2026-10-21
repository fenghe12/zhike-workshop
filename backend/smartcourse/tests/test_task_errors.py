import subprocess
import unittest
from app.task_errors import task_error_message


class TaskErrorTests(unittest.TestCase):
    def test_ssh_details_are_not_exposed(self):
        error = subprocess.CalledProcessError(255, ['ssh', '-i', '/Users/private/key', 'private-host'])
        message = task_error_message(error)
        self.assertIn('华为实例', message)
        self.assertNotIn('/Users', message)
        self.assertNotIn('private-host', message)

    def test_input_validation_remains_actionable(self):
        self.assertEqual(task_error_message(ValueError('讲稿缺少第 3 页')), '讲稿缺少第 3 页')
