import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.narration import prepare_narration


class Gateway:
    def __init__(self):
        self.calls = 0

    def respond_json(self, *args, **kwargs):
        self.calls += 1
        return {'pages':[{'page_id':1,'script_text':'A spoken explanation.','source_issues':[]}]}


class NarrationTests(unittest.TestCase):
    def test_incomplete_cached_pages_are_regenerated(self):
        gateway=Gateway()
        source={'language_code':'en','pages':[{'page_id':1,'script_text':'Content'}]}
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'narration.json'
            prepare_narration(source,gateway,output)
            cached=json.loads(output.read_text())
            cached['pages']=[]
            output.write_text(json.dumps(cached))
            prepare_narration(source,gateway,output)
            self.assertEqual(gateway.calls,2)
            self.assertEqual(len(json.loads(output.read_text())['pages']),1)

    def test_content_rejection_prevents_publication_and_uses_slide_facts(self):
        source={'pages':[{'page_id':1,'script_text':'Incorrect old draft',
                          'key_points':['Threshold 2.5 gives 6.5.']}]}
        failed={'passed':False,'checks':[{'met':False,'reason':'Changed threshold'}]}
        with tempfile.TemporaryDirectory() as folder, patch('app.course_content_review.review_course_content',return_value=failed) as review:
            output=Path(folder)/'narration.json'
            with self.assertRaisesRegex(ValueError,'Changed threshold'):
                prepare_narration(source,Gateway(),output,review_content=True)
            self.assertFalse(output.exists())
            self.assertEqual(review.call_count,3)
            context=review.call_args.kwargs['source_context']
            self.assertEqual(context['slidePages'][0]['content'],['Threshold 2.5 gives 6.5.'])
            self.assertNotIn('Incorrect old draft',str(context))

    def test_overlength_response_is_revised_before_publication(self):
        class RevisingGateway:
            calls = []
            def respond_json(self, prompt, **kwargs):
                self.calls.append(prompt)
                return {'pages':[{'page_id':1,'script_text':'文'*90 if len(self.calls)==1 else '简短完整讲解。'}]}
        with tempfile.TemporaryDirectory() as folder:
            gateway = RevisingGateway()
            output = Path(folder)/'narration.json'
            prepare_narration({'language_code':'zh-CN','pages':[{'page_id':1,'script_text':'原文'}]},
                              gateway,output,target_duration_seconds=10)
            self.assertEqual(len(gateway.calls),2)
            self.assertIn('超过 80 字限制',gateway.calls[1])
            self.assertEqual(json.loads(output.read_text())['pages'][0]['script_text'],'简短完整讲解。')
            self.assertTrue(output.with_name('narration.rejected-1.json').exists())

    def test_invalid_output_has_bounded_retries(self):
        gateway = Gateway()
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'narration.json'
            with self.assertRaisesRegex(ValueError,'三次修订'):
                prepare_narration({'pages':[{'page_id':2}]},gateway,output)
            self.assertEqual(gateway.calls,3)
            self.assertFalse(output.exists())

    def test_duration_budget_uses_language_code_and_display_names(self):
        for fields in ({'target_language':'English'},
                       {'target_language':'英语'},
                       {'target_language':'English','language_code':'en-US'}):
            with self.subTest(fields=fields), tempfile.TemporaryDirectory() as folder:
                output = Path(folder)/'narration.json'
                prepare_narration({**fields,'pages':[{'page_id':1,'script_text':'Content'}]},
                                  Gateway(),output,target_duration_seconds=60)
                request = json.loads(output.with_suffix('.request.json').read_text())
                self.assertEqual(request['maximum_characters_per_page'],720)

    def test_nonfinite_duration_rejected_before_model_call(self):
        for duration in (float('nan'),float('inf'),float('-inf')):
            gateway = Gateway()
            with tempfile.TemporaryDirectory() as folder, self.assertRaisesRegex(ValueError,'目标口播时长无效'):
                prepare_narration({'pages':[{'page_id':1}]},gateway,Path(folder)/'narration.json',
                                  target_duration_seconds=duration)
            self.assertEqual(gateway.calls,0)

    def test_cache_requires_same_job_and_same_source(self):
        gateway = Gateway()
        source = {'task_id':'first','language_code':'en','pages':[{'page_id':1,'script_text':'Content'}]}
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)/'narration.json'
            prepare_narration(source,gateway,output)
            prepare_narration(source,gateway,output)
            self.assertEqual(gateway.calls,1)
            source['task_id']='second'
            prepare_narration(source,gateway,output)
            self.assertEqual(gateway.calls,2)
            source['pages'][0]['script_text']='Changed content'
            prepare_narration(source,gateway,output)
            self.assertEqual(gateway.calls,3)

    def test_missing_page_does_not_publish(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)/'narration.json'
            with self.assertRaises(ValueError):
                prepare_narration({'task_id':'first','pages':[{'page_id':1},{'page_id':2}]},Gateway(),output)
            self.assertFalse(output.exists())

    def test_preparation_does_not_modify_original_structure(self):
        source={'task_id':'first','pages':[{'page_id':1,'script_text':'Original content'}]}
        with tempfile.TemporaryDirectory() as folder:
            output=prepare_narration(source,Gateway(),Path(folder)/'narration.json')
            self.assertEqual(source['pages'][0]['script_text'],'Original content')
            self.assertEqual(json.loads(output.read_text())['pages'][0]['script_source'],'narration_agent')


if __name__=='__main__':
    unittest.main()
