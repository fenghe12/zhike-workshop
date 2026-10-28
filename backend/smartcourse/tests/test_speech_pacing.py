import unittest
import tempfile,json
from pathlib import Path
import numpy as np
from app.speech_pacing import pacing_report,stabilize_pcm


class SpeechPacingTests(unittest.TestCase):
    def fixture(self):
        texts=['Hello everyone welcome to the introductory course on Artificial Intelligence.',
               'Today we will jointly unveil the mystery of Artificial Intelligence.',
               'First let us get to know what Artificial Intelligence is.']
        durations=[4.28,8.44,4.48];rate=24000;sentences=[];parts=[];cursor=0
        for index,(text,seconds) in enumerate(zip(texts,durations)):
            if index:parts.append(np.zeros(2880,dtype=np.float32));cursor+=2880
            part=np.full(round(seconds*rate),.1*(index+1),dtype=np.float32)
            sentences.append({'text':text,'startSample':cursor,'endSample':cursor+len(part)})
            parts.append(part);cursor+=len(part)
        return np.concatenate(parts),rate,sentences

    def test_report_identifies_the_slow_sentence_without_flagging_steady_speech(self):
        audio,rate,sentences=self.fixture()
        report=pacing_report(sentences,rate,'en-US')
        self.assertFalse(report['passed']);self.assertEqual([row['index'] for row in report['issues']],[1])
        steady=[{**row,'startSample':index*120000,'endSample':index*120000+110000} for index,row in enumerate(sentences)]
        self.assertTrue(pacing_report(steady,rate,'en')['passed'])
        self.assertIsNone(pacing_report(sentences[:1],rate,'en')['passed'])
        self.assertIsNone(pacing_report(sentences,rate,'de')['passed'])

    def test_only_outlier_is_regenerated_and_other_audio_samples_are_preserved(self):
        audio,rate,sentences=self.fixture();called=[]
        def generate(text):called.append(text);return np.full(4*rate,.25,dtype=np.float32)
        result,timing,report=stabilize_pcm(audio,rate,sentences,'en',generate)
        self.assertEqual(called,[sentences[1]['text']]);self.assertTrue(report['passed'])
        for index in [0,2]:
            before=audio[sentences[index]['startSample']:sentences[index]['endSample']]
            after=result[timing[index]['startSample']:timing[index]['endSample']]
            np.testing.assert_array_equal(before,after)
        self.assertEqual([row['text'] for row in timing],[row['text'] for row in sentences])

    def test_normal_synthesize_entry_automatically_detects_and_repairs_pace(self):
        import soundfile as sf
        from agents.cosyvoice_engine import CosyVoiceEngine
        audio,rate,sentences=self.fixture()
        class Tensor:
            def __init__(self,value):self.value=value
            def detach(self):return self
            def cpu(self):return self
            def numpy(self):return self.value
        class Model:
            sample_rate=rate
            def __init__(self):self.calls=[]
            def inference_cross_lingual(self,text,*args,**kwargs):
                self.calls.append(text)
                seconds=[4.28,8.44,4.48,4][min(len(self.calls)-1,3)]
                yield {'tts_speech':Tensor(np.full((1,round(seconds*rate)),.1,dtype=np.float32))}
        with tempfile.TemporaryDirectory() as folder:
            folder=Path(folder);reference=folder/'reference.wav';destination=folder/'generated.wav'
            sf.write(reference,np.full(3*rate,.1,dtype=np.float32),rate)
            engine=CosyVoiceEngine();engine._model=Model();engine._load=lambda:None
            engine.synthesize(' '.join(row['text'] for row in sentences),str(reference),str(destination),'en')
            report=json.loads(destination.with_suffix('.timing.json').read_text())['pacingReview']
            self.assertTrue(report['passed']);self.assertEqual(len(report['repairs']),1)
            self.assertEqual(len(engine._model.calls),4)
            self.assertEqual(report['repairs'][0]['index'],1)

    def test_retries_are_bounded_then_time_correction_is_measured(self):
        audio,rate,sentences=self.fixture();called=[]
        def generate(text):called.append(text);return audio[sentences[1]['startSample']:sentences[1]['endSample']]
        result,timing,report=stabilize_pcm(audio,rate,sentences,'en',generate)
        self.assertEqual(len(called),3);self.assertTrue(report['passed'])
        self.assertGreater(report['repairs'][0]['tempoFactor'],1)
        self.assertLess(len(result),len(audio))


if __name__=='__main__':unittest.main()
