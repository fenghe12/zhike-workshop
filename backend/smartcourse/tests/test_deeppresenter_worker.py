import fcntl
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


class WorkerTests(unittest.TestCase):
    def load(self, generate):
        path = Path(__file__).parents[1] / 'app/deeppresenter_worker.py'
        spec = importlib.util.spec_from_file_location('worker_under_test', path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', {'deeppresenter_course': SimpleNamespace(generate_course=generate)}):
            spec.loader.exec_module(module)
        return module

    def test_active_lock_prevents_duplicate_generation(self):
        generate = Mock()
        module = self.load(generate)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'request.json').write_text('{}')
            with (root / 'execution.lock').open('a') as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(RuntimeError, '仍在执行'):
                    module.main(root / 'request.json')
            generate.assert_not_called()
            self.assertFalse((root / 'result.json').exists())

    def test_generation_failure_is_persisted(self):
        module = self.load(Mock(side_effect=RuntimeError('生成测试失败')))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'request.json').write_text('{}')
            with self.assertRaises(RuntimeError):
                module.main(root / 'request.json')
            self.assertEqual(json.loads((root / 'result.json').read_text())['status'], 'failed')
