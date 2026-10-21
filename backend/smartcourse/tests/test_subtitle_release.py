import json
import tempfile
import unittest
from pathlib import Path

from app.patch_release import _edit_page_subtitle


class SubtitleReleaseTests(unittest.TestCase):
    def test_only_selected_page_is_changed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            srt=root/'subtitles.srt'
            srt.write_text('1\n00:00:00,000 --> 00:00:05,000\n权重 w i\n\n'
                           '2\n00:00:05,000 --> 00:00:10,000\n权重 w i\n',encoding='utf-8')
            timeline=root/'timeline.json'
            timeline.write_text(json.dumps({'pages':[
                {'page_id':1,'start_time':0,'end_time':5},
                {'page_id':2,'start_time':5,'end_time':10},
            ]}),encoding='utf-8')
            self.assertEqual(_edit_page_subtitle(srt,timeline,1,'w i','wᵢ'),1)
            result=srt.read_text(encoding='utf-8')
            self.assertIn('权重 wᵢ',result)
            self.assertEqual(result.count('权重 w i'),1)


if __name__=='__main__':
    unittest.main()
