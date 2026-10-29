import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.narration_style import review_teaching_style
from app.narration import prepare_narration
from app.upload_lecture import generate_upload_lecture
from app.topic_lecture import generate_topic_lecture
from app.full_pipeline import FullPipelineRunner
from app.config import Settings


class NarrationStyleTests(unittest.TestCase):
    def test_reporting_a_slide_is_detected_in_all_eight_languages(self):
        for text in ['随后，幻灯片介绍了1956年的达特茅斯研讨会。',
                     '幻灯片将该研讨会与从事计算机研究的人员联系起来。',
                     'The slide then introduces the Dartmouth workshop in 1956.',
                     'The slide associates the workshop with researchers.',
                     'このスライドでは会議を紹介します。', '이 슬라이드에서는 회의를 소개합니다.',
                     'Diese Folie zeigt die Entwicklung der Forschung.',
                     'Cette diapositive présente les origines de cette discipline.',
                     'Этот слайд показывает развитие науки.',
                     'Esta diapositiva presenta los orígenes de la disciplina.']:
            with self.subTest(text=text):self.assertFalse(review_teaching_style(text)['passed'])
        for text in ['1956年，达特茅斯研讨会召开。请比较右侧两条曲线。',
                     'The workshop took place in 1956. Compare the two curves.',
                     '本页讲稿。', 'この会議は1956年に開催されました。']:
            with self.subTest(text=text):self.assertTrue(review_teaching_style(text)['passed'])

    def test_generated_upload_script_retries_the_affected_page_and_keeps_facts(self):
        class Gateway:
            def __init__(self):self.calls=[]
            def respond_json(self,prompt,**kwargs):
                self.calls.append(prompt)
                if len(self.calls)==1:return {'script_text':'The slide introduces the Dartmouth workshop in 1956.'}
                return {'script_text':'The Dartmouth workshop took place in 1956.'}
        with tempfile.TemporaryDirectory() as directory:
            gateway=Gateway();source={'pages':[{'page_id':1,'title':'Dartmouth','key_points':['1956']}]}
            result=generate_upload_lecture(source,gateway,'en-US',directory)
            self.assertEqual(len(gateway.calls),2)
            self.assertIn('Dartmouth',result[0]['script_text']);self.assertIn('1956',result[0]['script_text'])
            self.assertTrue(result[0]['narration_style_review']['passed'])
            generate_upload_lecture(source,gateway,'en-US',directory)
            self.assertEqual(len(gateway.calls),2)

    def test_style_retry_exhaustion_continues_with_warning_and_does_not_restart_in_s3(self):
        gateway=Mock();gateway.respond_json.return_value={'script_text':'幻灯片介绍了1956年的达特茅斯研讨会。'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            pages=generate_upload_lecture({'pages':[{'page_id':1,'title':'人工智能起源'}]},gateway,'zh-CN',root/'s1')
            self.assertEqual(gateway.respond_json.call_count,4)
            self.assertFalse(pages[0]['narration_style_review']['passed'])
            self.assertIn('narration_warning',pages[0])
            output=prepare_narration({'pages':pages},gateway,root/'s3/narration.json',preserve_script=True)
            self.assertEqual(gateway.respond_json.call_count,4)
            self.assertFalse(json.loads(output.read_text())['pages'][0]['narration_style_review']['passed'])

    def test_legacy_automatic_script_is_corrected_before_voice_but_docx_is_preserved(self):
        bad='随后，幻灯片介绍了1956年的达特茅斯研讨会。'
        fixed='1956年，达特茅斯研讨会召开。'
        gateway=Mock();gateway.respond_json.return_value={'pages':[{'page_id':1,'script_text':fixed}]}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            source={'language_code':'zh-CN','pages':[{'page_id':1,'script_text':bad,'script_source':'translation_agent'}]}
            output=prepare_narration(source,gateway,root/'narration.json',preserve_script=True)
            self.assertEqual(json.loads(output.read_text())['pages'][0]['script_text'],fixed)
            self.assertEqual(source['pages'][0]['script_text'],bad)
            output=prepare_narration(source,gateway,root/'docx.json',preserve_script=True,enforce_direct_style=False)
            self.assertEqual(json.loads(output.read_text()),source)
            self.assertEqual(gateway.respond_json.call_count,1)

    def test_topic_model_uses_same_style_check(self):
        bad,good=Mock(),Mock()
        bad.json.return_value={'choices':[{'message':{'content':'幻灯片介绍了1956年的达特茅斯研讨会。'}}]}
        good.json.return_value={'choices':[{'message':{'content':'1956年，达特茅斯研讨会召开。'}}]}
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,{'SMARTCOURSE_REMOTE_MEDIA':'0'}),patch('app.topic_lecture.requests.post',side_effect=[bad,good]) as model:
            result=generate_topic_lecture([{'page_id':1,'title':'人工智能起源'}],audience='本科生',minutes=1,output=Path(directory)/'lecture.json')
            self.assertEqual(model.call_count,2)
            self.assertTrue(result[0]['narration_style_review']['passed'])

    def test_translation_retries_reporting_style_but_preserves_authored_docx_wording(self):
        class Gateway:
            calls=0
            def respond_json(self,*args,**kwargs):
                self.calls+=1
                text='幻灯片介绍了1956年召开的达特茅斯研讨会，它通常被视为人工智能学科的起点。' if self.calls==1 else '1956年，达特茅斯研讨会召开。这次会议通常被视为人工智能学科的起点。'
                return {'script_text':text,'passed':True,'semantic_similarity':1,'terminology_coverage':1,
                        'formula_number_proper_name_accuracy':1,'contextual_consistency':1}
        source={'page_id':1,'script_text':'The Dartmouth workshop was held in 1956 and is commonly viewed as a starting point for artificial intelligence.',
                'script_source':'generated_from_slide'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);runner=FullPipelineRunner(Settings(root/'data',root/'artifacts','http://unused','fixture','','127.0.0.1',0))
            runner.gateway=Gateway()
            result,report=runner._translate_page(source,'Simplified Chinese')
            self.assertEqual(runner.gateway.calls,2)
            self.assertTrue(report['passed']);self.assertTrue(result['narration_style_review']['passed'])
            self.assertIn('1956',result['script_text'])
            runner.gateway=Gateway()
            result,report=runner._translate_page({**source,'script_source':'user_docx'},'Simplified Chinese')
            self.assertEqual(runner.gateway.calls,1);self.assertTrue(report['passed'])
            self.assertIn('幻灯片介绍了',result['script_text'])


if __name__=='__main__':unittest.main()
