import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error, request

from app.account_policy import POLICY_VERSION
from app.config import Settings
from app.server import SmartCourseApplication, make_handler
from app.store import JsonStore
from app.task_model import create_task


class UserFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        root = Path(self.folder.name)
        self.app = SmartCourseApplication(Settings(root/'data', root/'artifacts', 'http://invalid', 'none', '', '127.0.0.1', 0), pipeline_runner=object())
        consent = {'version': POLICY_VERSION, 'termsAccepted': True, 'privacyAccepted': True}
        self.owner = self.app.store.register('feedback-owner', 'test-password', 'Owner', policy_consent=consent)
        self.other = self.app.store.register('feedback-other', 'test-password', 'Other', policy_consent=consent)
        self.task = create_task({'name':'Course', 'mode':'topic', 'targetLanguages':['日语'], 'inputs':{'topic':'Networks'}})
        self.task.update(createdBy=self.owner['user']['id'], status='completed', outputs={'s1':{'pageCount':12}})
        self.app.store.transact(lambda data: data['tasks'].update({self.task['id']:self.task}))
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.app.task_queue.close()
        self.folder.cleanup()

    def call(self, payload=None, token=None, task_id=None):
        headers = {'Content-Type':'application/json'}
        if token is None:
            token = self.owner['accessToken']
        if token:
            headers['Authorization'] = 'Bearer '+token
        url = self.base+'/v1/feedback'+('?taskId='+task_id if task_id else '')
        req = request.Request(url, data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
        try:
            with request.urlopen(req, timeout=10) as response:
                return response.status, json.load(response)
        except error.HTTPError as exc:
            return exc.code, json.load(exc)

    def test_multiple_categories_rating_and_context_survive_store_reload(self):
        status, row = self.call({'taskId':self.task['id'], 'rating':2,
                                'categories':['translation','speech','subtitles','speech'],
                                'comment':'The third page has an error.', 'language':'ja-JP',
                                'page':3, 'playbackSeconds':20.5, 'createdBy':'forged'})
        self.assertEqual(status, 201, row)
        self.assertEqual(row['categories'], ['translation','speech','subtitles'])
        self.assertEqual(row['createdBy'], self.owner['user']['id'])
        self.assertEqual(row['taskSnapshot']['name'], 'Course')
        stored = JsonStore(self.app.store.path).snapshot()['userFeedback'][row['id']]
        self.assertEqual(stored['page'], 3)
        self.assertEqual(stored['playbackSeconds'], 20.5)
        self.assertEqual(self.call(task_id=self.task['id'])[1][0]['id'], row['id'])

    def test_other_account_cannot_read_or_submit_course_feedback(self):
        self.call({'taskId':self.task['id'], 'rating':4})
        token = self.other['accessToken']
        self.assertEqual(self.call(token=token)[1], [])
        self.assertEqual(self.call(token=token, task_id=self.task['id'])[0], 403)
        self.assertEqual(self.call({'taskId':self.task['id'], 'rating':1}, token=token)[0], 403)
        self.assertEqual(self.call(token='')[0], 401)
        self.assertEqual(self.call({'comment':'test'}, token='')[0], 401)

    def test_general_feedback_and_validation(self):
        self.assertEqual(self.call({'comment':'The upload page could be clearer.', 'categories':['other']})[0], 201)
        invalid = [{'rating':0}, {'rating':True}, {'rating':6}, {'rating':2.5},
                   {'categories':['unknown'], 'rating':3}, {'comment':[]}, {},
                   {'rating':3, 'page':1}, {'rating':3, 'taskId':[]},
                   {'rating':3, 'taskId':self.task['id'], 'language':'英语'},
                   {'rating':3, 'taskId':self.task['id'], 'page':13},
                   {'rating':3, 'taskId':self.task['id'], 'playbackSeconds':float('nan')}]
        for payload in invalid:
            with self.subTest(payload=payload):
                self.assertEqual(self.call(payload)[0], 400)


if __name__ == '__main__':
    unittest.main()
