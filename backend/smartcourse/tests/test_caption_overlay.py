import json
import os
import shutil
import subprocess
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from app.caption_overlay import caption_events
from agents.s5_compose_agent import ComposeAgent


class CaptionOverlayTests(unittest.TestCase):
    def test_timeline_preserves_inclusive_ends_gaps_and_first_matching_overlap(self):
        subtitles=[(.2,.4,'First'),(.4,.6,'Second'),(.5,.8,'Third')]
        result=caption_events(subtitles,25,30)
        frames=[]
        for event in result:frames.extend([event['text']]*event['frames'])
        expected=[next((text for start,end,text in subtitles if start<=index/25<=end),None) for index in range(30)]
        self.assertEqual(frames,expected)
        self.assertEqual(sum(event['frames'] for event in result),30)

    def test_ffmpeg_output_preserves_frame_count_gaps_avatar_area_and_original_on_error(self):
        fonts=[os.environ.get('SMARTCOURSE_CJK_FONT',''),'/System/Library/Fonts/Hiragino Sans GB.ttc',
               '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
        font=next((p for p in fonts if p and Path(p).is_file()),None)
        if not font or not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
            self.skipTest('FFmpeg and a font are required for media validation')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'source.mp4';output=root/'output.mp4';srt=root/'caption.srt'
            subprocess.run([shutil.which('ffmpeg'),'-v','error','-nostdin','-f','lavfi','-i',
                'color=c=0xD0D0D0:s=960x540:r=25:d=2','-f','lavfi','-i','sine=frequency=440:sample_rate=24000:duration=2',
                '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest',str(source)],check=True)
            srt.write_text('1\n00:00:00,200 --> 00:00:00,600\nFirst explanation.\n\n'
                           '2\n00:00:01,000 --> 00:00:01,400\nSecond explanation.\n')
            bbox={1:{'img_w':960,'img_h':540,'x_px':780,'y_px':320,'size_px':180}}
            agent=ComposeAgent(root)
            with patch.dict(os.environ,{'SMARTCOURSE_CJK_FONT':font}):
                agent._burn_subtitles(source,srt,output,bbox)
            probe=json.loads(subprocess.check_output([shutil.which('ffprobe'),'-v','error','-select_streams','v:0',
                '-show_entries','stream=nb_frames,avg_frame_rate:format=duration','-of','json',str(output)]))
            self.assertEqual(probe['streams'][0]['nb_frames'],'50')
            self.assertEqual(Fraction(probe['streams'][0]['avg_frame_rate']),25)
            capture=cv2.VideoCapture(str(output))
            def frame(index):
                capture.set(cv2.CAP_PROP_POS_FRAMES,index);ok,image=capture.read();self.assertTrue(ok);return image
            blank=frame(0);visible=frame(8);gap=frame(20);second=frame(30);after=frame(45)
            self.assertLess(visible[420:530,40:610].mean(),blank[420:530,40:610].mean()-10)
            self.assertLess(second[420:530,40:610].mean(),blank[420:530,40:610].mean()-10)
            np.testing.assert_allclose(gap,blank,atol=4)
            np.testing.assert_allclose(after,blank,atol=4)
            np.testing.assert_allclose(visible[:,750:],blank[:,750:],atol=4)
            capture.release()
            record=json.loads(output.with_suffix('.caption-render.json').read_text())
            self.assertEqual(record['uniqueImages'],3)
            self.assertEqual(record['frameCount'],50)
            original_size=source.stat().st_size
            with patch.dict(os.environ,{'SMARTCOURSE_CJK_FONT':str(root/'missing.ttf')}):
                with self.assertRaises(OSError):agent._burn_subtitles(source,srt,source,bbox)
            self.assertEqual(source.stat().st_size,original_size)


if __name__=='__main__':unittest.main()
