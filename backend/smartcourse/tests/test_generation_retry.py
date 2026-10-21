import json
import tempfile
import unittest
from pathlib import Path
from app.generation_retry import reviewed_generation_requirements


class GenerationRetryTests(unittest.TestCase):
    def test_no_rejection_keeps_original_request(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(reviewed_generation_requirements(temporary, '原要求'), '原要求')

    def test_rejection_changes_request_and_observation_reuses_revision(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / 'source-content-review.json'
            report.write_text(json.dumps({'passed': False, 'checks': [
                {'requirement': '不添加数值', 'met': False, 'reason': '新增示例',
                 'sources': [{'quote': '(1,1)'}]}]}))
            revised = reviewed_generation_requirements(root, '原要求')
            self.assertIn('新增示例', revised)
            self.assertNotEqual(revised, '原要求')
            self.assertEqual(reviewed_generation_requirements(root, '原要求'), revised)
            self.assertEqual(json.loads((root / 'generation-retry.json').read_text())['revision'], 1)
            report.write_text('{"passed":true}')
            self.assertEqual(reviewed_generation_requirements(root, '原要求'), revised)

    def test_passing_review_does_not_invalidate_result(self):
        with tempfile.TemporaryDirectory() as temporary:
            (Path(temporary) / 'source-content-review.json').write_text('{"passed":true}')
            self.assertEqual(reviewed_generation_requirements(temporary, '原要求'), '原要求')
