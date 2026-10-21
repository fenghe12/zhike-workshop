import json
import os
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
from agents.s3_tts_agent import TTSAgent
from agents.flashhead_agent import FlashHeadAvatarAgent


class MediaParallelTests(unittest.TestCase):
    def test_alignment_starts_before_last_page_synthesis_and_resume_uses_same_job(self):
        event=threading.Event();calls=[];alignments=[]
        class Engine:
            def synthesize(self,text,speaker_prompt,output_path,language):
                if calls and not event.wait(2):raise AssertionError('alignment did not overlap synthesis')
                calls.append(text);sf.write(output_path,np.full(24000,.1),24000)
                Path(output_path).with_suffix('.timing.json').write_text(json.dumps({'inputText':text,'sampleRate':24000,'totalSamples':24000,'sentences':[{'text':text,'startSample':0,'endSample':24000}]}));return 1.0
        class Aligner:
            def get_sentence_timestamps(self,wav_path,language):
                alignments.append(wav_path);event.set();return [{'text':'A sentence.','start':0,'end':1}]
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);ref=root/'reference.wav';sf.write(ref,np.full(72000,.1),24000)
            source=root/'source.json';source.write_text(json.dumps({'task_id':'one-job','language_code':'en','pages':[{'page_id':1,'title':'Display-only course heading','script_text':'A sentence.'},{'page_id':2,'title':'Second heading','script_text':'Another sentence.'}]}))
            agent=TTSAgent(workspace_root=folder,speaker_prompt=str(ref),tts_speed=1.0);agent.tts_engine=Engine();agent.aligner=Aligner()
            result=agent.run('en',str(source));self.assertEqual(result['pages'],2);self.assertEqual(len(calls),2)
            self.assertEqual(calls,['A sentence.','Another sentence.'])
            agent.run('en',str(source));self.assertEqual(len(calls),2);self.assertEqual(len(alignments),2)

    def test_avatar_workers_use_distinct_devices_and_preserve_page_order(self):
        barrier=threading.Barrier(2);devices=[]
        def generate(audio,photo,output,device=None):
            devices.append(device);barrier.wait(2);Path(output).write_bytes(b'model output')
        def normalize(raw,audio,destination,duration):shutil.copy2(raw,destination)
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'SMARTCOURSE_REMOTE_MEDIA':'1','SMARTCOURSE_AVATAR_WORKERS':'2'}):
            root=Path(folder);photo=root/'photo.png';photo.write_bytes(b'photo');audio=root/'voice.wav';audio.write_bytes(b'voice')
            timeline=root/'timeline.json';timeline.write_text(json.dumps({'pages':[{'page_id':i,'wav_path':str(audio),'duration':1} for i in [1,2]]}))
            with patch('app.remote_media.generate_avatar',generate),patch.object(FlashHeadAvatarAgent,'normalize_video',staticmethod(normalize)):
                agent=FlashHeadAvatarAgent(root,photo);result=agent.run('ja',timeline)
                self.assertEqual(set(devices),{0,1});self.assertEqual([p['page_id'] for p in result['pages']],[1,2])
                agent.run('ja',timeline);self.assertEqual(len(devices),2)


if __name__=='__main__':unittest.main()
