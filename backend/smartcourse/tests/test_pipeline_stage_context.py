import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from app.config import Settings
from app.full_pipeline import FullPipelineRunner


class PipelineStageContextTests(unittest.TestCase):
    def test_final_composition_receives_new_speech_warning_instead_of_previous_attempt(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runner = FullPipelineRunner(Settings(root/'data', root/'artifacts',
                'http://unused', 'fixture', '', '127.0.0.1', 0))
            task = {'mode':'topic', 'targetLanguages':['英语'],
                    'assets':{'referenceAudio':{'path':'unused.wav'},'referenceImage':{'path':'unused.png'}},
                    'outputs':{'s1':{},'s2':{},'s3':{'languages':{'en-US':{'warning':'Old warning'}}}}}
            previous = copy.deepcopy(task)
            current_warning = '第 8 页超过建议长度，保留完整讲稿继续生成。'
            runner._run_s3 = Mock(return_value={'languages':{'en-US':
                {'durationSeconds':3,'warning':current_warning}}})
            runner._run_s4 = Mock(return_value={})
            runner._run_s5 = Mock(side_effect=lambda current, *_:
                {'warning':current['outputs']['s3']['languages']['en-US']['warning']})
            result = runner.run('fixture-task',task,lambda *_:None,start_stage=3)
            self.assertEqual(result['stages']['s5']['warning'],current_warning)
            self.assertEqual(task,previous)


if __name__ == '__main__':
    unittest.main()
