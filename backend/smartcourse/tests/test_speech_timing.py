import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import soundfile as sf
from agents.cosyvoice_engine import CosyVoiceEngine
from app.speech_timing import generated_sentences


class Tensor:
    def __init__(self, size): self.values=np.full(size,.1,dtype=np.float32)
    def detach(self): return self
    def cpu(self): return self
    def numpy(self): return self.values


class Model:
    sample_rate=24000
    def inference_cross_lingual(self,text,*args,**kwargs):
        yield {'tts_speech':Tensor(4800 if 'First' in text else 7200)}


class SpeechTimingTests(unittest.TestCase):
    def test_sentence_times_follow_generated_sample_counts(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ,{'SMARTCOURSE_REMOTE_MEDIA':'0'}):
            root=Path(folder);reference=root/'reference.wav';output=root/'output.wav'
            sf.write(reference,np.full(72000,.1),24000)
            engine=CosyVoiceEngine();engine._model=Model()
            duration=engine.synthesize('First. Second.',str(reference),str(output),'en')
            self.assertAlmostEqual(duration,.62)
            rows=generated_sentences(output,'First. Second.',duration)
            self.assertEqual(rows,[{'text':'First.','start':0,'end':.2},
                                   {'text':'Second.','start':.32,'end':.62}])

    def test_different_script_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            wav=Path(folder)/'audio.wav'
            wav.with_suffix('.timing.json').write_text(json.dumps({'inputText':'Different'}))
            with self.assertRaises(ValueError):generated_sentences(wav,'Expected',2)

    def test_samples_outside_audio_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            wav=Path(folder)/'audio.wav'
            wav.with_suffix('.timing.json').write_text(json.dumps({'inputText':'Text','sampleRate':24000,'totalSamples':48001}))
            with self.assertRaises(ValueError):generated_sentences(wav,'Text',2)


if __name__=='__main__':unittest.main()
