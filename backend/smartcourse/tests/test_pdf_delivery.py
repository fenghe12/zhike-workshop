import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from app.pdf_delivery import package_pdf_result


class PdfDeliveryTests(unittest.TestCase):
    def test_completed_pdf_repackaging_uses_pdf_pipeline(self):
        from app.delivery import package_completed_task
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);task_root=root/'tasks'/'task-one'
            (task_root/'s1').mkdir(parents=True)
            (task_root/'s1/course_structure.json').write_text('{"input_mode":"existing_pdf"}')
            task={'id':'task-one','name':'课程','status':'completed','outputs':{'s5':{'languages':{'ko-KR':{}}}}}
            result_files={'video':str(task_root/'delivery/ko-KR/course.mp4'),
                          'coursePdf':str(task_root/'delivery/ko-KR/course.pdf'),'pageVideos':[]}
            with patch('app.pdf_delivery.package_pdf_result',return_value=result_files) as package:
                result=package_completed_task(task,root)
            package.assert_called_once()
            self.assertEqual(result['languages']['ko-KR']['coursePdf'],'/artifacts/tasks/task-one/delivery/ko-KR/course.pdf')
            self.assertNotIn('coursePptx',result['languages']['ko-KR'])

    def test_bundle_has_pdf_and_no_false_pptx_link_or_internal_audio_path(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            for name in ('video.mp4','s2/ko-KR/translated.pdf','s3/ko-KR/lecture.txt','s1/lecture.txt',
                         's2/ko-KR/lecture.txt','runtime/ko-KR/s3_output/subtitles.srt'):
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'test fixture')
            (root/'runtime/ko-KR/s3_output/timeline.json').write_text(json.dumps({'pages':[{'page_id':1,
                'duration':1,'start_time':0,'end_time':1,'wav_path':'/private/server/voice.wav'}]}))
            def export(video,timeline,directory):
                directory.mkdir(parents=True);page=directory/'page-001.mp4';page.write_bytes(b'fixture')
                return [{'page_id':1,'path':str(page),'durationSeconds':1}]
            with patch('app.pdf_delivery.export_page_videos',side_effect=export):
                result=package_pdf_result(root,'ko-KR','课程',root/'video.mp4')
            self.assertNotIn('course.pptx',Path(result['offlinePage']).read_text())
            self.assertNotIn('/private/',Path(result['timeline']).read_text())
            with ZipFile(result['downloadBundle']) as archive:
                self.assertIn('course.pdf',archive.namelist())
                self.assertIn('pages/page-001.mp4',archive.namelist())
                self.assertNotIn('course.pptx',archive.namelist())
