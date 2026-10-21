import tempfile
import unittest
from pathlib import Path

from app.config import Settings
from app.server import SmartCourseApplication, TaskCancelled
from app.task_model import create_task, replace_task_assets, retry_stage


class TaskLifecycleTests(unittest.TestCase):
    def test_retry_does_not_mark_unexecuted_stages_complete(self):
        task=create_task({"name":"Course", "mode":"topic", "inputs":{"topic":"Networks"}, "targetLanguages":["德语"]})
        with self.assertRaises(ValueError):
            retry_stage(task,3)
        self.assertNotEqual(task['stages'][0]['status'],'completed')
    def test_replacing_voice_invalidates_only_media_stages(self):
        task=create_task({"name":"Course", "mode":"topic", "inputs":{"topic":"Networks"}, "targetLanguages":["德语"]})
        task['status']='completed'
        task['outputs']={f's{i}':{'result':i} for i in range(1,6)}
        for stage in task['stages']:stage.update(status='completed',progress=100)
        replace_task_assets(task,{'referenceAudio':{'path':'new-reference.wav'}})
        self.assertEqual(task['status'],'needs_regeneration')
        self.assertEqual(task['currentStage'],3)
        self.assertEqual(set(task['outputs']),{'s1','s2'})
        self.assertEqual(task['stages'][1]['progress'],100)
        self.assertEqual(task['stages'][2]['progress'],0)

    def test_cancelled_task_is_not_revived_by_late_progress(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            app=SmartCourseApplication(Settings(root/'data',root/'artifacts','http://invalid','test','','127.0.0.1',0))
            task=app.add_task({'name':'Course','mode':'topic','inputs':{'topic':'Networks'},'targetLanguages':['德语'],'autoExecute':False},None)
            app.mutate_task(task['id'],lambda value,_:value.update(status='cancelled'))
            with self.assertRaises(TaskCancelled):
                app._progress_callback(task['id'])(2,'completed',100,{'done':True})
            self.assertEqual(app.get_task(task['id'])['status'],'cancelled')

    def test_audio_padding_matches_video_frames(self):
        import numpy as np
        from scipy.io import wavfile
        from agents.s3_tts_agent import append_silence_to_wav
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'audio.wav'
            original=np.ones(16000,dtype=np.int16)*100
            wavfile.write(path,16000,original)
            duration=append_silence_to_wav(str(path),.75,25)
            self.assertAlmostEqual(duration,1.76)
            rate, actual=wavfile.read(path)
            self.assertTrue(np.array_equal(actual[:len(original)],original))
            self.assertAlmostEqual(len(actual)/rate*25,round(len(actual)/rate*25))
