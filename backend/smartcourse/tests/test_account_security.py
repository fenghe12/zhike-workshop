"""Exercise account protection and consent with isolated persistent test storage."""
import base64
import io
import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib import request, error

from PIL import Image
from app.account_policy import POLICY_VERSION, MEDIA_VERSION
from app.account_security import AccountSecurity, AuthSecurityError
from app.config import Settings
from app.server import SmartCourseApplication, make_handler


class AccountProtectionTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        root=Path(self.folder.name)
        self.app=SmartCourseApplication(Settings(data_root=root/'data',artifact_root=root/'artifacts',
            gateway_url='http://invalid',gateway_model='none',gateway_token='',host='127.0.0.1',port=0),pipeline_runner=object())
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.app))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.app.task_queue.close();self.folder.cleanup()

    def call(self,path,value=None,token=None,method=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        req=request.Request(self.base+path,data=None if value is None else json.dumps(value).encode(),headers=headers,method=method)
        try:
            with request.urlopen(req,timeout=10) as response:return response.status,json.load(response)
        except error.HTTPError as exc:return exc.code,json.load(exc)

    def payload(self,account='account@example.test'):
        status,challenge=self.call('/v1/auth/captcha');self.assertEqual(status,200)
        with self.app.account_security.connect() as db:
            answer=db.execute('SELECT answer FROM challenges WHERE id=?',(challenge['id'],)).fetchone()[0]
        return {'account':account,'password':'course-password','name':'测试用户','institution':'测试单位',
                'captchaId':challenge['id'],'captchaCode':answer,'termsAccepted':True,
                'privacyAccepted':True,'policyVersion':POLICY_VERSION}

    def registered(self,account='account@example.test'):
        status,result=self.call('/v1/auth/register',self.payload(account));self.assertEqual(status,201,result)
        return result

    def test_public_challenge_is_png_and_does_not_return_answer(self):
        status,value=self.call('/v1/auth/captcha')
        self.assertEqual(status,200);self.assertNotIn('answer',value)
        raw=base64.b64decode(value['image'].split(',')[1]);image=Image.open(io.BytesIO(raw))
        self.assertEqual(image.format,'PNG');self.assertEqual(value['expiresInSeconds'],300)

    def test_register_requires_both_policy_and_captcha(self):
        data=self.payload();data['termsAccepted']=False
        self.assertEqual(self.call('/v1/auth/register',data)[0],400)
        data=self.payload();data.pop('captchaCode')
        self.assertEqual(self.call('/v1/auth/register',data)[0],400)
        self.assertEqual(len(self.app.store.snapshot()['users']),0)

    def test_registration_records_consent_without_password_leak(self):
        result=self.registered();self.assertNotIn('passwordHash',result['user'])
        self.assertEqual(result['user']['policyConsent']['version'],POLICY_VERSION)
        self.assertTrue(result['user']['policyConsent']['privacyAccepted'])
        self.assertEqual(self.call('/v1/auth/session',{},result['accessToken'])[1]['agreementRequired'],False)

    def test_wrong_captcha_is_consumed_and_cannot_be_reused(self):
        value=self.payload();correct=value['captchaCode'];value['captchaCode']='WRONG'
        self.assertEqual(self.call('/v1/auth/register',value)[0],400)
        value['captchaCode']=correct
        self.assertEqual(self.call('/v1/auth/register',value)[0],400)

    def test_expired_challenge_fails(self):
        value=self.payload()
        with self.app.account_security.connect() as db:
            db.execute('UPDATE challenges SET expires=? WHERE id=?',(time.time()-1,value['captchaId']))
        self.assertEqual(self.call('/v1/auth/register',value)[0],400)

    def test_password_login_and_logout(self):
        self.registered();data=self.payload();data['password']='wrong-password'
        self.assertEqual(self.call('/v1/auth/login',data)[0],400)
        status,result=self.call('/v1/auth/login',self.payload());self.assertEqual(status,200)
        token=result['accessToken'];self.assertEqual(self.call('/v1/auth/logout',{},token)[0],200)
        self.assertEqual(self.call('/v1/auth/session',{},token)[0],401)

    def test_old_account_must_acknowledge_policy_before_new_upload(self):
        result=self.app.store.register('legacy@example.test','legacy-password','原账号')
        token=result['accessToken'];status,session=self.call('/v1/auth/session',{},token)
        self.assertEqual(status,200);self.assertTrue(session['agreementRequired'])
        self.assertEqual(self.call('/v1/uploads',{'filename':'x.png','kind':'image','contentBase64':'eA=='},token)[0],403)
        status,accepted=self.call('/v1/auth/consent',{'termsAccepted':True,'privacyAccepted':True,'policyVersion':POLICY_VERSION},token)
        self.assertEqual(status,200);self.assertEqual(accepted['user']['id'],result['user']['id'])

    def test_media_needs_separate_explicit_consent_and_remains_private(self):
        owner=self.registered();image=io.BytesIO();Image.new('RGB',(512,512),'white').save(image,format='PNG')
        data={'filename':'teacher.png','kind':'image','contentBase64':base64.b64encode(image.getvalue()).decode()}
        self.assertEqual(self.call('/v1/uploads',data,owner['accessToken'])[0],400)
        data['mediaConsent']={'authorized':True,'version':MEDIA_VERSION}
        status,uploaded=self.call('/v1/uploads',data,owner['accessToken']);self.assertEqual(status,201)
        self.assertEqual(uploaded['consent']['userId'],owner['user']['id'])
        other=self.registered('another@example.test')
        self.assertEqual(self.call(uploaded['path'],token=other['accessToken'])[0],403)

    def test_login_requires_consent_even_for_previously_registered_user(self):
        self.registered();value=self.payload();value['privacyAccepted']=False
        self.assertEqual(self.call('/v1/auth/login',value)[0],400)

    def test_attempt_limit_is_persistent(self):
        security=self.app.account_security
        for _ in range(12):security.failed('one-client')
        second=AccountSecurity(security.path)
        with self.assertRaises(AuthSecurityError) as caught:second.check_attempts('one-client')
        self.assertEqual(caught.exception.status,429)

    def test_old_session_expires_after_seven_days(self):
        result=self.registered();token=result['accessToken']
        def expire(data):
            record=data['tokens'][token];record.pop('expiresAt');record['createdAt']=(datetime.now(timezone.utc)-timedelta(days=8)).isoformat()
        self.app.store.transact(expire)
        self.assertEqual(self.call('/v1/auth/session',{},token)[0],401)
