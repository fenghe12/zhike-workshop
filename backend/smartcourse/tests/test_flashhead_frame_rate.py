import json
import importlib.util
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path

from agents.flashhead_agent import FlashHeadAvatarAgent


class FlashHeadRestoreFrameRateTests(unittest.TestCase):
    def helper(self):
        path=Path(__file__).resolve().parents[3]/'recovery/huawei/ensure_flashhead_fps.py'
        spec=importlib.util.spec_from_file_location('flashhead_restore_fps',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module.ensure_frame_rate

    def test_restored_twenty_fps_config_is_updated_before_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'flash_head.yaml'
            path.write_text('infer_params:\n  tgt_fps: 20\n  sample_rate: 16000\n')
            ensure=self.helper()
            self.assertTrue(ensure(path)['changed'])
            self.assertIn('tgt_fps: 25',path.read_text())
            self.assertIn('sample_rate: 16000',path.read_text())
            self.assertFalse(ensure(path)['changed'])

    def test_ambiguous_frame_rate_config_is_rejected_without_modification(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'flash_head.yaml';original='tgt_fps: 20\ntgt_fps: 24\n'
            path.write_text(original)
            with self.assertRaises(ValueError):self.helper()(path)
            self.assertEqual(path.read_text(),original)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class FlashHeadFrameRateTests(unittest.TestCase):
    def check_rate(self,fps):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);raw=root/'raw.mp4';audio=root/'voice.wav';target=root/'normalized.mp4'
            subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i',f'color=c=blue:s=64x64:r={fps}',
                            '-t','0.4','-c:v','libx264','-pix_fmt','yuv420p',str(raw)],check=True)
            with wave.open(str(audio),'wb') as stream:
                stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(24000);stream.writeframes(b'\0\0'*9600)
            if fps==20:
                with self.assertRaisesRegex(RuntimeError,'原始生成帧率'):
                    FlashHeadAvatarAgent.normalize_video(raw,audio,target,.4)
                self.assertFalse(target.exists())
            else:
                FlashHeadAvatarAgent.normalize_video(raw,audio,target,.4)
                value=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0',
                    '-show_entries','stream=r_frame_rate,nb_frames','-of','json',str(target)]))['streams'][0]
                self.assertEqual(value['r_frame_rate'],'25/1');self.assertEqual(int(value['nb_frames']),10)

    def test_rejects_twenty_fps_instead_of_hiding_it_with_resampling(self):self.check_rate(20)
    def test_accepts_twenty_five_fps_and_preserves_frame_count(self):self.check_rate(25)
