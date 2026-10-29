import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib import request, error
from app.account_policy import POLICY_VERSION
from app.config import Settings
from app.server import SmartCourseApplication, make_handler
from app.task_model import create_task
from app.admin_console import parse_filters, is_admin
from app.usage_tracking import UsageStore


class AdminTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();root=Path(self.folder.name)
        self.app=SmartCourseApplication(Settings(root/'data',root/'artifacts','http://invalid','none','','127.0.0.1',0),pipeline_runner=object())
        policy={'version':POLICY_VERSION,'termsAccepted':True,'privacyAccepted':True}
        self.admin=self.app.store.register('admin-account','test-password','Admin',policy_consent=policy)
        self.owner=self.app.store.register('real-owner','test-password','Teacher',policy_consent=policy)
        self.other=self.app.store.register('other-account','test-password','Other',policy_consent=policy)
        self.test=self.app.store.register('deploy@example.test','test-password','Test',policy_consent=policy)
        (root/'data/admin-access.json').write_text(json.dumps({'accounts':['admin-account']}))
        self.task=self.make_task(self.owner,'Course A','completed',['日语'],100)
        self.failed=self.make_task(self.owner,'Course B','failed',['英语','法语'],300)
        self.test_task=self.make_task(self.test,'Test course','completed',['中文'],200)
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.app));self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.server.server_port)

    def make_task(self, user, name, status, languages, seconds):
        task=create_task({'name':name,'mode':'topic','targetLanguages':languages,'inputs':{'topic':'Neural networks','courseProfile':{'domain':'computing','audience':'undergraduate','topics':['神经网络']}}})
        task.update(createdBy=user['user']['id'],status=status,createdAt='2026-10-27T16:30:00Z',updatedAt='2026-10-28T02:00:00Z',outputs={'s1':{'pageCount':3},'s3':{'languages':{'ja-JP':{'durationSeconds':120}}}})
        if status=='completed':task['outputs']['s5']={'languages':{code:{'video':'/artifacts/example.mp4','durationSeconds':120} for code in (['ja-JP'] if languages==['日语'] else ['zh-CN'])}}
        task['stages'][0].update(status='completed',elapsedSeconds=seconds);task['stages'][1].update(status='failed' if status=='failed' else 'completed',elapsedSeconds=seconds*2)
        self.app.store.transact(lambda d:d['tasks'].update({task['id']:task}));return task

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.app.task_queue.close();self.folder.cleanup()

    def call(self,path,body=None,user=None,method=None):
        token=(user or self.admin)['accessToken'] if user is not False else ''
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        req=request.Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
        try:
            with request.urlopen(req,timeout=10) as r:return r.status,json.load(r)
        except error.HTTPError as e:return e.code,json.load(e)

    def test_permission_is_server_configured_not_user_supplied(self):
        for path in ['/v1/admin/overview','/v1/admin/options','/v1/admin/tasks','/v1/admin/feedback','/v1/studio/admin-metrics']:
            self.assertEqual(self.call(path,user=False)[0],401)
            self.assertEqual(self.call(path,user=self.owner)[0],403)
            self.assertEqual(self.call(path)[0],200)
        self.app.store.transact(lambda d:d['users']['real-owner'].update(isAdmin=True,role='admin'))
        self.assertEqual(self.call('/v1/admin/overview',user=self.owner)[0],403)
        self.assertFalse(self.call('/v1/admin/access',user=self.owner)[1]['isAdmin'])

    def test_feedback_filters_multiselect_status_audit_and_private_notes(self):
        with patch('app.user_feedback.utc_now',return_value='2026-10-28T03:00:00Z'):
            _,first=self.call('/v1/feedback',{'taskId':self.task['id'],'language':'日语','rating':2,'categories':['translation','speech'],'comment':'Actual feedback'},user=self.owner)
            self.call('/v1/feedback',{'taskId':self.failed['id'],'language':'英语','rating':5,'categories':['layout'],'comment':'Another result'},user=self.owner)
        status,result=self.call('/v1/admin/feedback?category=translation,subtitles&rating=2&language=ja-JP&start=2026-10-28&end=2026-10-28')
        self.assertEqual(status,200);self.assertEqual(result['total'],1);self.assertEqual(result['averageRating'],2)
        self.assertEqual(result['rows'][0]['id'],first['id'])
        path='/v1/admin/feedback/'+first['id']
        self.assertEqual(self.call(path,{'status':'planned','adminNote':'Internal plan'},user=self.owner,method='PUT')[0],403)
        self.assertEqual(self.call(path,{'status':'planned','adminNote':'Internal plan'},method='PUT')[0],200)
        stored=self.app.store.snapshot()['userFeedback'][first['id']];self.assertEqual(stored['adminHistory'][0]['by'],self.admin['user']['id'])
        own=self.call('/v1/feedback',user=self.owner)[1]
        self.assertTrue(all('adminNote' not in row and 'adminHistory' not in row for row in own))
        self.assertEqual(self.call('/v1/admin/feedback?feedbackStatus=planned')[1]['total'],1)
        groups=self.call('/v1/studio/admin-metrics')[1]['qualityByConfiguration']
        self.assertTrue(any(row['language']=='ja-JP' and row['averageRating']==2 for row in groups))

    def test_overview_counts_samples_date_and_excludes_test_data(self):
        status,result=self.call('/v1/admin/overview?start=2026-10-28&end=2026-10-28')
        self.assertEqual(status,200);self.assertEqual(result['summary']['tasks'],2)
        stage=result['stageTimes'][0];self.assertEqual(stage['samples'],2);self.assertEqual(stage['averageSeconds'],200)
        self.assertIsNone(result['stageTimes'][2]['averageSeconds'])
        self.assertEqual(result['courseDuration']['samples'],1)
        self.assertNotIn('markets',result)
        owner=next(u for u in result['users'] if u['id']==self.owner['user']['id'])
        self.assertEqual(owner['courseDuration']['samples'],1)
        self.assertEqual(self.call('/v1/admin/overview?includeTests=1')[1]['summary']['tasks'],3)
        self.assertEqual(self.call('/v1/admin/overview?language=ja-JP')[1]['summary']['tasks'],1)
        single=self.call('/v1/admin/overview?userId='+self.owner['user']['id'])[1]
        self.assertEqual(single['summary']['users'],1)
        self.assertEqual(single['summary']['newUsers'],1)
        self.assertEqual(self.call('/v1/admin/overview?end=2026-10-27')[1]['summary']['tasks'],0)
        self.assertEqual(self.call('/v1/admin/overview?start=invalid')[0],400)
        self.assertEqual(self.call('/v1/admin/overview?pageSize=200')[0],400)
        encoded=json.dumps(result);self.assertNotIn('passwordHash',encoded);self.assertNotIn('accessToken',encoded)

    def test_usage_events_persist_deduplicate_and_enforce_course_access(self):
        body={'kind':'result_play','taskId':self.task['id'],'language':'ja-JP','eventId':'one-event'}
        self.assertEqual(self.call('/v1/usage',body,user=self.owner)[0],201)
        self.call('/v1/usage',body,user=self.owner)
        self.assertEqual(self.call('/v1/usage',body,user=self.other)[0],403)
        self.assertEqual(self.call('/v1/usage',{'kind':'login'},user=self.owner)[0],400)
        rows=UsageStore(self.app.settings.data_root).rows();self.assertEqual(len(rows),1)
        self.assertEqual(self.call('/v1/admin/overview')[1]['summary']['plays'],1)

    def test_course_video_durations_are_separate_from_processing_time_and_audio(self):
        self.app.mutate_task(self.task['id'],lambda task,data:task['outputs']['s5']['languages'].update({'en-US':{'video':'/artifacts/english.mp4','durationSeconds':600},'fr-FR':{'video':'/artifacts/french.mp4'}}))
        self.app.mutate_task(self.task['id'],lambda task,data:task.update(targetLanguages=['日语','英语','法语']))
        _,result=self.call('/v1/admin/overview')
        summary=result['courseDuration']
        self.assertEqual(summary['generatedVersions'],3)
        self.assertEqual(summary['samples'],2)
        self.assertEqual(summary['unrecordedVersions'],1)
        self.assertEqual(summary['totalSeconds'],720)
        self.assertEqual(summary['averageSeconds'],360)
        self.assertEqual({r['key']:r['count'] for r in summary['distribution']}['10_20'],1)
        _,japanese=self.call('/v1/admin/overview?language=ja-JP')
        self.assertEqual(japanese['courseDuration']['totalSeconds'],120)
        _,filtered=self.call('/v1/admin/tasks?durationBucket=10_20')
        self.assertEqual(filtered['total'],1)
        self.assertEqual(filtered['rows'][0]['courseVersions'][0]['language'],'en-US')
        self.assertEqual(self.call('/v1/admin/overview?durationBucket=under_1')[1]['courseDuration']['samples'],0)
        self.assertEqual(self.call('/v1/admin/overview?durationBucket=invalid')[0],400)
        self.assertNotIn('markets',self.call('/v1/course-profile/options')[1])

    def test_resource_wait_is_accumulated_and_reset_on_retry(self):
        from app.task_model import retry_stage
        callback=self.app._progress_callback(self.task['id'])
        self.app.mutate_task(self.task['id'],lambda task,data:retry_stage(task,1))
        for when,status,progress in [(100,'running',0),(120,'queued',5),(125,'queued',5),(140,'running',10),(150,'completed',100)]:
            with patch('app.server.time.time',return_value=when):callback(1,status,progress,{})
        stage=self.app.get_task(self.task['id'])['stages'][0]
        self.assertEqual(stage['queueWaitSeconds'],20)
        self.assertEqual(stage['elapsedSeconds'],50)
        self.app.mutate_task(self.task['id'],lambda task,data:retry_stage(task,1))
        self.assertNotIn('queueWaitSeconds',self.app.get_task(self.task['id'])['stages'][0])

    def test_new_course_profile_validation(self):
        from app.course_profile import normalize_profile
        value=normalize_profile({'domain':'computing','markets':['japan'],'topics':[' AI ']})
        self.assertNotIn('markets',value);self.assertEqual(value['topics'],['AI'])
        for value in [[],{'domain':[]},{'topics':'bad'}]:
            with self.assertRaises(ValueError):normalize_profile(value)


if __name__=='__main__':unittest.main()
