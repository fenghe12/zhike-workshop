"""Stateful checks for interrupted inputs, account tools, and rerun accounting."""
import base64
import io
import json
import tempfile
import threading
import unittest
import os
import time
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib import request, error

from PIL import Image
from app.account_policy import POLICY_VERSION, MEDIA_VERSION
from app.config import Settings
from app.server import SmartCourseApplication, make_handler
from app.task_model import create_task


class ProductServicesTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.app = SmartCourseApplication(Settings(data_root=root/'data', artifact_root=root/'artifacts',
            workspace_root=root/'artifacts/tasks', gateway_url='http://invalid', gateway_model='none',
            gateway_token='', host='127.0.0.1', port=0), pipeline_runner=object())
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:'+str(self.server.server_port)
        self.user = self.app.store.register('owner-account', 'initial-password', 'Owner',
            policy_consent={'version': POLICY_VERSION, 'termsAccepted': True, 'privacyAccepted': True})
        self.other = self.app.store.register('other-account', 'other-password', 'Other',
            policy_consent={'version': POLICY_VERSION, 'termsAccepted': True, 'privacyAccepted': True})

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.app.task_queue.close()
        self.folder.cleanup()

    def call(self, path, value=None, token=None, method=None, raw=None):
        headers = {'Content-Type': 'application/octet-stream' if raw is not None else 'application/json',
                   'Authorization': 'Bearer '+(token or self.user['accessToken'])}
        body = raw if raw is not None else None if value is None else json.dumps(value).encode()
        req = request.Request(self.base+path, data=body, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=10) as response:
                return response.status, json.load(response)
        except error.HTTPError as exc:
            return exc.code, json.load(exc)

    def image(self):
        output = io.BytesIO()
        Image.new('RGB', (512, 512), '#789a83').save(output, 'PNG')
        return output.getvalue()

    def begin_image(self, content):
        return self.call('/v1/uploads/resumable', {'filename': 'teacher.png', 'kind': 'image',
            'size': len(content), 'mediaConsent': {'authorized': True, 'version': MEDIA_VERSION}})

    def test_parts_survive_service_recreation_and_complete_once(self):
        content = self.image()
        status, result = self.begin_image(content)
        self.assertEqual(status, 201, result)
        identifier = result['id']
        status, result = self.call('/v1/uploads/resumable/'+identifier+'/parts/0', method='PUT', raw=content)
        self.assertEqual(status, 200, result)
        from app.resumable_uploads import ResumableUploads
        self.app.product_services.uploads = ResumableUploads(self.app.settings.data_root,
            self.app.settings.artifact_root, self.app.store)
        status, result = self.call('/v1/uploads/resumable/'+identifier)
        self.assertEqual(result['received'], [0])
        status, first = self.call('/v1/uploads/resumable/'+identifier+'/complete', {})
        self.assertEqual(status, 201, first)
        status, second = self.call('/v1/uploads/resumable/'+identifier+'/complete', {})
        self.assertEqual(first, second)
        self.assertEqual(len(self.app.store.snapshot()['uploads']), 1)
        path = self.app.settings.artifact_root/first['path'].removeprefix('/artifacts/')
        self.assertEqual(path.read_bytes(), content)

    def test_other_account_cannot_access_write_or_delete_parts(self):
        content = self.image()
        _, result = self.begin_image(content)
        path = '/v1/uploads/resumable/'+result['id']
        token = self.other['accessToken']
        self.assertEqual(self.call(path, token=token)[0], 403)
        self.assertEqual(self.call(path+'/parts/0', token=token, method='PUT', raw=content)[0], 403)
        self.assertEqual(self.call(path, token=token, method='DELETE')[0], 403)

    def test_five_users_upload_concurrently_without_sharing_assets(self):
        users = [self.app.store.register('parallel-owner-'+str(i), 'test-password', 'Owner',
            policy_consent={'version': POLICY_VERSION, 'termsAccepted': True, 'privacyAccepted': True})
            for i in range(5)]
        content = self.image()
        def upload(user):
            token = user['accessToken']
            status, state = self.call('/v1/uploads/resumable', {'filename': 'teacher.png', 'kind': 'image',
                'size': len(content), 'mediaConsent': {'authorized': True, 'version': MEDIA_VERSION}}, token=token)
            self.assertEqual(status, 201, state)
            prefix = '/v1/uploads/resumable/'+state['id']
            self.assertEqual(self.call(prefix+'/parts/0', method='PUT', raw=content, token=token)[0], 200)
            status, result = self.call(prefix+'/complete', {}, token=token)
            self.assertEqual(status, 201, result)
            owned = self.call('/v1/uploads', token=token)[1]
            self.assertEqual([item['id'] for item in owned], [result['id']])
            return result['id']
        with ThreadPoolExecutor(max_workers=5) as pool:
            identifiers = list(pool.map(upload, users))
        self.assertEqual(len(set(identifiers)), 5)

    def test_incomplete_upload_does_not_create_asset(self):
        _, result = self.begin_image(self.image())
        status, _ = self.call('/v1/uploads/resumable/'+result['id']+'/complete', {})
        self.assertEqual(status, 400)
        self.assertFalse(self.app.store.snapshot().get('uploads'))

    def test_multiple_parts_resume_after_recreation(self):
        output = io.BytesIO()
        Image.frombytes('RGB', (768, 768), os.urandom(768*768*3)).save(output, 'PNG')
        content = output.getvalue()
        _, state = self.begin_image(content)
        self.assertGreater(state['count'], 1)
        prefix = '/v1/uploads/resumable/'+state['id']
        first = content[:state['chunkSize']]
        self.assertEqual(self.call(prefix+'/parts/0', method='PUT', raw=first)[0], 200)
        from app.resumable_uploads import ResumableUploads
        self.app.product_services.uploads = ResumableUploads(self.app.settings.data_root,
            self.app.settings.artifact_root, self.app.store)
        self.assertEqual(self.call(prefix)[1]['received'], [0])
        self.assertEqual(self.call(prefix+'/complete', {})[0], 400)
        for index in range(1, state['count']):
            part = content[index*state['chunkSize']:(index+1)*state['chunkSize']]
            self.assertEqual(self.call(prefix+'/parts/'+str(index), method='PUT', raw=part)[0], 200)
        status, result = self.call(prefix+'/complete', {})
        self.assertEqual(status, 201, result)
        path = self.app.settings.artifact_root/result['path'].removeprefix('/artifacts/')
        self.assertEqual(path.read_bytes(), content)

    def test_invalid_image_fails_final_validation(self):
        content = b'not a picture'
        _, result = self.begin_image(content)
        path = '/v1/uploads/resumable/'+result['id']
        self.call(path+'/parts/0', method='PUT', raw=content)
        self.assertEqual(self.call(path+'/complete', {})[0], 400)

    def test_password_change_requires_current_password_and_revokes_old_sessions(self):
        old = self.user['accessToken']
        bad = {'currentPassword': 'incorrect', 'password': 'new-password', 'confirmPassword': 'new-password'}
        self.assertEqual(self.call('/v1/auth/password/change', bad)[0], 400)
        bad['currentPassword'] = 'initial-password'
        status, value = self.call('/v1/auth/password/change', bad)
        self.assertEqual(status, 200, value)
        self.assertIsNone(self.app.store.user_for_token(old))
        self.assertIsNotNone(self.app.store.user_for_token(value['accessToken']))

    def test_email_reset_is_single_use_and_revokes_old_session(self):
        messages = []
        self.app.product_services.email.sender = lambda address, code: messages.append((address, code))
        address = 'owner@example.test'
        self.app.store.bind_email(self.user['user']['id'], address)
        self.app.product_services.email.send(address, 'reset', 'local-reset')
        self.assertEqual(messages[0][0], address)
        payload = {'email': address, 'code': messages[0][1], 'password': 'reset-password', 'confirmPassword': 'reset-password'}
        status, result = self.call('/v1/auth/password/reset', payload)
        self.assertEqual(status, 200, result)
        self.assertIsNone(self.app.store.user_for_token(self.user['accessToken']))
        self.assertEqual(self.call('/v1/auth/password/reset', payload)[0], 400)

    def test_email_is_not_verified_by_an_incorrect_or_different_purpose_code(self):
        messages = []
        self.app.product_services.email.sender = lambda address, code: messages.append((address, code))
        self.app.product_services.email.send('owner@example.test', 'register', 'local-register')
        status, _ = self.call('/v1/auth/email/confirm', {'email': 'owner@example.test', 'code': messages[0][1]})
        self.assertEqual(status, 400)
        self.assertNotIn('emailVerifiedAt', self.app.store.user_for_token(self.user['accessToken']))

    def test_storage_preferences_are_owner_scoped(self):
        status, value = self.call('/v1/settings/storage', {'retentionDays': 30, 'maxTaskBudgetCny': 5}, method='PUT')
        self.assertEqual(status, 200, value)
        self.assertEqual(self.call('/v1/settings/storage')[1]['retentionDays'], 30)
        self.assertEqual(self.call('/v1/settings/storage', token=self.other['accessToken'])[1]['retentionDays'], 0)

    def test_estimate_route_is_not_mistaken_for_task_identifier(self):
        status, value = self.call('/v1/tasks/estimate', {'durationMinutes': 1, 'totalPages': 1,
            'targetLanguages': ['zh-CN', 'en-US', 'ja-JP', 'ru-RU', 'fr-FR', 'es-ES', 'de-DE']})
        self.assertEqual(status, 200, value)
        self.assertGreater(value['estimatedComputeCny'][1], value['estimatedComputeCny'][0])

    def test_server_rejects_generation_above_saved_budget(self):
        self.call('/v1/settings/storage', {'retentionDays': 0, 'maxTaskBudgetCny': .1}, method='PUT')
        task = self.app.add_task({'name': 'Budget check', 'mode': 'topic', 'targetLanguages': ['英语'],
            'inputs': {'topic': 'Example', 'durationMinutes': 10}}, self.user['user']['id'])
        status, result = self.call('/v1/tasks/'+task['id']+'/execute', {'startStage': 1})
        self.assertEqual(status, 409, result)
        self.assertIn('预算', result['message'])
        self.assertFalse(self.app.store.snapshot().get('executionQueue'))

    def test_native_lease_uses_cumulative_duration_from_creation(self):
        from app.remote_media import media_service_status
        state = self.app.settings.data_root/'test-compute-state.json'
        now = time.time()*1000
        state.write_text(json.dumps({'status': 'RUNNING', 'lease': {'enable': True, 'type': 'TIMING',
            'create_at': now-10800000, 'update_at': now-3600000, 'duration': 7200000}}))
        with patch.dict(os.environ, {'SMARTCOURSE_REMOTE_MEDIA': '1', 'SMARTCOURSE_MEDIA_SERVICE_ENABLED': '1',
            'SMARTCOURSE_REMOTE_STATE': str(state), 'SMARTCOURSE_COMPUTE_OWNER': ''}):
            self.assertEqual(media_service_status(), 'LEASE_EXPIRED')

    def test_cloud_control_requires_separate_operator_authorization(self):
        status, _ = self.call('/v1/compute/control')
        self.assertIn(status, [403, 503])
        self.assertFalse(self.call('/v1/compute/status')[1]['controllerAvailable'])

    def test_deleting_course_removes_owned_files_but_preserves_other_users(self):
        task = self.app.add_task({'name': 'Delete sample', 'mode': 'topic', 'targetLanguages': ['中文'],
            'inputs': {'topic': 'Example'}}, self.user['user']['id'])
        folder = self.app.settings.workspace_root/task['id']
        folder.mkdir(parents=True)
        (folder/'course.txt').write_text('Generated course')
        self.assertEqual(self.call('/v1/tasks/'+task['id'], token=self.other['accessToken'], method='DELETE')[0], 403)
        self.assertTrue(folder.exists())
        status, value = self.call('/v1/tasks/'+task['id'], method='DELETE')
        self.assertEqual(status, 200, value)
        self.assertFalse(folder.exists())

    def test_queue_resets_all_later_timings_and_preserves_earlier_outputs(self):
        task = self.app.add_task({'name': 'Retry sample', 'mode': 'topic', 'targetLanguages': ['中文'],
            'inputs': {'topic': 'Example'}}, self.user['user']['id'])
        def completed(value, _data):
            value.update(status='completed', overallProgress=100)
            for stage in value['stages']:
                stage.update(status='completed', progress=100, startedAt='old', completedAt='old', elapsedSeconds=999)
                value['outputs'][stage['key']] = {'old': stage['index']}
            value['outputs']['result'] = {'old': True}
        self.app.mutate_task(task['id'], completed)
        with patch.object(self.app.task_queue, 'start'):
            self.app.task_queue.submit(task['id'], 3)
        row = self.app.get_task(task['id'])
        self.assertEqual(row['overallProgress'], 40)
        self.assertIn('s1', row['outputs'])
        self.assertNotIn('result', row['outputs'])
        for stage in row['stages'][2:]:
            self.assertNotIn('startedAt', stage)
            self.assertNotIn('completedAt', stage)
            self.assertNotIn('elapsedSeconds', stage)
        self.assertIn('result', row['executionHistory'][-1]['outputs'])
