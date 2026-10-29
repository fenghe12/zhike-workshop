import copy
import json
import os
import unittest
from unittest.mock import patch

import test_course_studio as fixture
from app.account_security import AuthSecurityError


class InputAssistanceTests(unittest.TestCase):
    setUp=fixture.CourseStudioTests.setUp
    tearDown=fixture.CourseStudioTests.tearDown
    uid=fixture.CourseStudioTests.uid
    url=fixture.CourseStudioTests.url
    write=fixture.CourseStudioTests.write
    call=fixture.CourseStudioTests.call
    member=fixture.CourseStudioTests.member

    def writing(self,**values):
        payload={'label':'课程要求','purpose':'requirements','text':'Explain binary values.','language':'en-US',**values}
        return self.call('/v1/studio/assist-input',payload)

    def proposal(self,**values):
        return self.call('suggest-revision',{'instruction':'Make the page title clearer.','language':'en-US','page':2,'withImages':False,**values})

    def title_answer(self):
        return {'summary':'标题更具体。','questions':[],'changes':[{'page':2,'kind':'slide_text',
            'oldText':'Learning','text':'Model Training','reason':'明确学习的对象为模型训练。'}]}

    def test_writing_is_a_private_draft_and_acceptance_does_not_submit_a_course(self):
        before=copy.deepcopy(self.app.store.snapshot()['tasks'])
        self.app.pipeline_runner.gateway.respond_json.return_value={'summary':'整理教学要求。','suggestions':[
            {'text':'Explain binary place values with a short worked example.','reason':'明确学习内容和讲解方式。'}],'questions':[]}
        status,value=self.writing();self.assertEqual(status,200,value)
        self.assertEqual(self.call('/v1/studio/assist-input',user='other')[1],[])
        self.assertEqual(self.call('/v1/studio/assist-input/'+value['id']+'/accept',{'index':0},user='other')[0],403)
        status,accepted=self.call('/v1/studio/assist-input/'+value['id']+'/accept',{'index':0,'mode':'replace'})
        self.assertEqual(status,200);self.assertIn('binary',accepted['text'])
        self.assertEqual(self.app.store.snapshot()['tasks'],before)
        self.app.execute_task.assert_not_called()
        self.assertEqual(self.call('/v1/studio/assist-input')[1][0]['status'],'accepted')
        self.assertEqual(self.call('/v1/studio/assist-input',{},user=None)[0],401)

    def test_empty_feedback_requests_information_instead_of_inventing_an_experience(self):
        model=self.app.pipeline_runner.gateway.respond_json
        model.side_effect=[{'summary':'错误示例','suggestions':[{'text':'语音太慢。','reason':'猜测问题'}],'questions':[]},
            {'summary':'请先简述实际问题。','suggestions':[],'questions':['哪一页出现了什么问题？']}]
        status,value=self.writing(purpose='feedback',text='');self.assertEqual(status,200,value)
        self.assertEqual(value['suggestions'],[]);self.assertEqual(model.call_count,2)

    def test_paused_model_returns_a_clear_error_without_spending_or_changing_input(self):
        with patch.dict(os.environ,{'SMARTCOURSE_COMPUTE_OWNER':'owned-test'}),patch('app.remote_media.media_service_status',return_value='STOPPED'):
            status,value=self.writing()
        self.assertEqual(status,409);self.assertIn('已保留',value['message']);self.app.pipeline_runner.gateway.respond_json.assert_not_called()

    def test_feedback_retries_invented_playback_symptoms_in_summary_or_suggestion(self):
        model=self.app.pipeline_runner.gateway.respond_json
        good={'summary':'第1页5.6秒起语速突然变慢。','suggestions':[{'text':'第1页5.6秒起语速突然变慢，希望讲解语速保持均匀。','reason':'保留用户描述的语速、页码和时间。'}],'questions':[]}
        for field in ('summary','suggestion'):
            with self.subTest(field=field):
                bad=copy.deepcopy(good)
                if field=='summary':bad['summary']='第1页5.6秒出现视频卡顿。'
                else:bad['suggestions'][0]['text']='第1页5.6秒开始播放变慢，建议改善视频流畅度。'
                model.reset_mock();model.side_effect=[bad,good]
                status,value=self.writing(purpose='feedback',text='第1页5.6秒开始突然变慢，希望语速更均匀',language='zh-CN')
                self.assertEqual(status,200,value);self.assertEqual(model.call_count,2)
                self.assertEqual(value['suggestions'],good['suggestions'])

    def test_feedback_preserves_explicitly_reported_speech_and_network_problems(self):
        answer={'summary':'用户同时报告了语速和网络加载问题。','suggestions':[{'text':'第1页语速很慢，并且网络加载时出现缓冲。','reason':'保留两个已经报告的问题。'}],'questions':[]}
        model=self.app.pipeline_runner.gateway.respond_json;model.return_value=answer
        status,value=self.writing(purpose='feedback',text='第1页语速很慢，网络加载也会缓冲。',language='zh-CN')
        self.assertEqual(status,200,value);self.assertEqual(model.call_count,1)
        self.assertEqual(value['suggestions'],answer['suggestions'])

    def test_ambiguous_slowdown_is_not_classified_as_playback_or_speech(self):
        before=copy.deepcopy(self.app.store.snapshot()['tasks'])
        model=self.app.pipeline_runner.gateway.respond_json
        status,value=self.writing(purpose='feedback',text='第1页5.6秒开始变慢',language='zh-CN')
        self.assertEqual(status,200,value);model.assert_not_called()
        self.assertEqual(value['suggestions'],[]);self.assertTrue(value['questions'])
        self.assertEqual(value['generationMode'],'local_clarification')
        self.assertIn('第1页5.6秒开始变慢',value['summary'])
        self.assertEqual(self.app.store.snapshot()['tasks'],before)

    def test_feedback_summary_can_distinguish_unreported_problems(self):
        good={'summary':'第1页语速变慢。用户未提及播放卡顿、加载或网络问题。','suggestions':[{'text':'第1页语速变慢。','reason':'保留实际报告。'}],'questions':[]}
        bad=copy.deepcopy(good);bad['summary']='未报告加载问题，但第1页播放变慢。'
        model=self.app.pipeline_runner.gateway.respond_json;model.side_effect=[bad,good]
        status,value=self.writing(purpose='feedback',text='第1页语速变慢',language='zh-CN')
        self.assertEqual(status,200,value);self.assertEqual(model.call_count,2)
        self.assertEqual(value['summary'],good['summary'])

    def test_preference_edit_does_not_restore_a_conflicting_account_default(self):
        self.app.store.transact(lambda data:data.setdefault('teachingMemories',{}).update({self.uid('owner'):{'enabled':True,'style':'先解释概念，再说明例子。'}}))
        good={'summary':'保留当前填写的讲授顺序。','suggestions':[{'text':'先举例，再讲原理。','reason':'仅整理表达。'}],'questions':[]}
        bad=copy.deepcopy(good);bad['suggestions'][0]['text']='先解释概念，再说明例子。'
        model=self.app.pipeline_runner.gateway.respond_json;model.side_effect=[bad,good]
        status,value=self.writing(purpose='memory',text='先举例，再讲原理',instruction='保持我的偏好，整理为一句',language='zh-CN')
        self.assertEqual(status,200,value);self.assertEqual(model.call_count,2)
        self.assertEqual(value['suggestions'],good['suggestions'])
        supplied=json.loads(model.call_args_list[0].args[0].rsplit('\n',1)[1])
        self.assertEqual(supplied['teachingPreference'],{})

    def test_grounded_title_suggestions_create_one_cpu_revision_and_optional_memory(self):
        answer=self.title_answer();wrong=copy.deepcopy(answer);wrong['changes'][0]['oldText']='Not in this slide'
        self.app.pipeline_runner.gateway.respond_json.side_effect=[wrong,answer]
        status,value=self.proposal();self.assertEqual(status,200,value)
        self.assertEqual(self.app.pipeline_runner.gateway.respond_json.call_count,2)
        self.assertEqual(value['changes'][0]['startStage'],5);self.assertNotIn('_snapshots',value)
        self.assertEqual(self.app.get_task(self.task['id'])['status'],'completed')
        payload={'suggestionId':value['id'],'selectedIds':['1'],'execute':False,'remember':True}
        status,applied=self.call('apply-suggestion',payload);self.assertEqual(status,200,applied)
        count=len(self.app.store.snapshot()['tasks'])
        again=self.call('apply-suggestion',payload)[1];self.assertEqual(applied['releaseTaskId'],again['releaseTaskId']);self.assertEqual(len(self.app.store.snapshot()['tasks']),count)
        self.assertEqual(applied['startStage'],5)
        self.assertEqual(self.app.studio.memory(applied['releaseTaskId'])['entries'][0]['value'],'Make the page title clearer.')
        self.assertEqual(self.app.studio.memory(self.task['id'])['entries'],[])
        self.app.execute_task.assert_not_called()

    def test_content_changes_invalidate_a_proposal_before_creating_a_version(self):
        self.app.pipeline_runner.gateway.respond_json.return_value=self.title_answer()
        _,value=self.proposal();count=len(self.app.store.snapshot()['tasks'])
        path=self.course_root/'s2/en-US/translated_structure.json';current=json.loads(path.read_text());current['pages'][1]['script_text']+=' Additional teacher instruction.';self.write(path,current)
        status,error=self.call('apply-suggestion',{'suggestionId':value['id'],'selectedIds':['1'],'execute':False})
        self.assertEqual(status,400);self.assertIn('已变化',error['message']);self.assertEqual(len(self.app.store.snapshot()['tasks']),count)

    def test_revision_permissions_and_suggestion_history_are_account_scoped(self):
        self.member('other','editor');self.member('reviewer','reviewer')
        self.app.pipeline_runner.gateway.respond_json.return_value=self.title_answer()
        _,value=self.proposal()
        self.assertEqual(self.call('apply-suggestion',{'suggestionId':value['id'],'selectedIds':['1']},user='other')[0],403)
        self.assertEqual(self.call('suggest-revision',{'instruction':'Fix title','page':2,'language':'en-US'},user='reviewer')[0],403)
        self.assertEqual(self.call(user='other')[1]['revisionSuggestions'],[])
        self.assertNotIn('revisionSuggestions',self.call(user='reviewer')[1])
        self.app.pipeline_runner.gateway.respond_json.return_value={'summary':'建议','suggestions':[{'text':'Training adjusts model weights.','reason':'保持原有概念。'}],'questions':[]}
        _,draft=self.call('/v1/studio/assist-input',{'courseId':self.task['id'],'purpose':'lecture','language':'en-US','label':'讲稿','text':'Training adjusts weights.'},user='other')
        self.member('other','learner');self.call('publish',{'status':'published'})
        self.assertEqual(self.call('/v1/studio/assist-input',user='other')[1],[])
        self.assertEqual(self.call('/v1/studio/assist-input/'+draft['id']+'/accept',{'index':0},user='other')[0],403)

    def test_wrong_language_script_is_retried_and_images_are_supplied(self):
        from PIL import Image
        folder=self.course_root/'s1/source-slide-images';folder.mkdir();Image.new('RGB',(64,64),'white').save(folder/'page_001.png');Image.new('RGB',(64,64),'white').save(folder/'page_002.png')
        good={'summary':'解释训练。','questions':[],'changes':[{'page':2,'kind':'script','text':'Training adjusts model weights using prediction errors. A smaller error indicates a better prediction.','reason':'以完整句子说明训练过程。'}]}
        bad=copy.deepcopy(good);bad['changes'][0]['text']='模型通过调整权重来减少预测误差。这是中文讲稿，需要翻译为目标语言才能用于英语课程。'
        model=self.app.pipeline_runner.gateway.respond_json;model.side_effect=[bad,good]
        status,value=self.proposal(withImages=True);self.assertEqual(status,200,value)
        self.assertEqual(model.call_count,2);self.assertEqual(value['imagePages'],[2]);self.assertTrue(model.call_args.kwargs['image_paths'])

    def test_explicit_auto_apply_preserves_a_draft_when_execution_is_paused(self):
        self.app.pipeline_runner.gateway.respond_json.return_value=self.title_answer()
        self.app.execute_task.side_effect=AuthSecurityError('计算已暂停。',409)
        status,value=self.proposal(autoApply=True);self.assertEqual(status,200,value)
        self.assertEqual(value['status'],'applied');self.assertIn('暂停',value['executionMessage'])
        self.assertIn(value['releaseTaskId'],self.app.store.snapshot()['tasks']);self.app.execute_task.assert_called_once()

    def test_invalid_page_changes_stop_after_three_local_retries(self):
        bad=self.title_answer();bad['changes'][0]['page']=99
        self.app.pipeline_runner.gateway.respond_json.return_value=bad
        status,value=self.proposal();self.assertEqual(status,400,value);self.assertEqual(self.app.pipeline_runner.gateway.respond_json.call_count,4)
        self.assertIn('3 次局部重试',value['message'])

    def test_learners_can_refine_questions_without_access_to_teacher_memory(self):
        self.member('learner','learner');self.call('publish',{'status':'published'})
        self.app.studio.update_memory(self.task['id'],self.uid('owner'),{'revision':0,'entries':[{'kind':'preference','name':'PRIVATE_TEACHER_SETTING','value':'PRIVATE_INSTRUCTOR_NOTE','pages':[1],'status':'accepted'}]})
        self.app.pipeline_runner.gateway.respond_json.return_value={'summary':'明确提问。','suggestions':[{'text':'How do weights change during training?','reason':'使问题指向本页概念。'}],'questions':[]}
        payload={'courseId':self.task['id'],'page':2,'language':'en-US','label':'学习提问','purpose':'question','text':'How do weights change?'}
        status,value=self.call('/v1/studio/assist-input',payload,user='learner');self.assertEqual(status,200,value)
        prompt=self.app.pipeline_runner.gateway.respond_json.call_args.args[0];self.assertNotIn('PRIVATE_INSTRUCTOR',prompt)
        payload['purpose']='lecture';self.assertEqual(self.call('/v1/studio/assist-input',payload,user='learner')[0],403)
