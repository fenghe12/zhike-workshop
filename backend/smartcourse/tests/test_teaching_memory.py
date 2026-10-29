import io
import json
import tempfile
import threading
import unittest
import zipfile
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib import error, request
from unittest.mock import Mock, patch

from app.account_policy import POLICY_VERSION
from app.config import Settings
from app.full_pipeline import FullPipelineRunner
from app.gateway import ResponsesGateway
from app.server import SmartCourseApplication, make_handler
from app.teaching_memory import apply_current_memory, read_memory, use_memory


class TeachingMemoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.settings = Settings(root/'data', root/'artifacts', 'http://model.local/v1/chat/completions',
                                 'fixture-model', 'fixture-token', '127.0.0.1', 0)
        self.app = SmartCourseApplication(self.settings, pipeline_runner=object())
        consent = {'version': POLICY_VERSION, 'termsAccepted': True, 'privacyAccepted': True}
        self.owner = self.app.store.register('memory-owner', 'test-password', 'Owner', policy_consent=consent)
        self.other = self.app.store.register('memory-other', 'test-password', 'Other', policy_consent=consent)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.app.task_queue.close()
        self.directory.cleanup()

    def call(self, path='/v1/settings/teaching-memory', payload=None, account=None, anonymous=False):
        headers = {'Content-Type': 'application/json'}
        if not anonymous:
            headers['Authorization'] = 'Bearer '+(account or self.owner)['accessToken']
        req = request.Request(self.base+path, headers=headers,
                              data=json.dumps(payload).encode() if payload is not None else None)
        try:
            with request.build_opener(request.ProxyHandler({})).open(req, timeout=10) as response:
                return response.status, json.load(response)
        except error.HTTPError as exc:
            return exc.code, json.load(exc)

    def sample(self, revision=0):
        return {'enabled': True, 'audience': 'Beginner students', 'style': 'Explain terms before examples.',
                'glossary': [{'source':'梯度下降','target':'gradient descent','language':'en-US'}],
                'revision': revision, 'createdBy': self.other['user']['id']}

    def test_authenticated_account_memory_is_persistent_isolated_and_clearable(self):
        self.assertEqual(self.call(anonymous=True)[0], 401)
        status, saved = self.call(payload=self.sample())
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved['revision'], 1)
        self.assertEqual(read_memory(self.app.store, self.owner['user']['id']), saved)
        self.assertEqual(self.call(account=self.other)[1]['glossary'], [])
        self.assertEqual(self.call(payload=self.sample())[0], 400)
        status, cleared = self.call(payload={'enabled': False, 'audience':'', 'style':'', 'glossary':[], 'revision':1})
        self.assertEqual(status, 200)
        self.assertFalse(cleared['enabled'])
        self.assertEqual(cleared['style'], '')
        self.assertEqual(cleared['glossary'], [])

    def test_task_freezes_server_owned_memory_and_rejects_cross_user_journal_reads(self):
        self.call(payload=self.sample())
        payload = {'name':'Memory course', 'mode':'topic', 'targetLanguages':['英语'],
                   'inputs':{'topic':'Gradient descent'}, 'teachingMemory':{'style':'forged'}, 'autoExecute':False}
        with patch('app.course_presets.bind_course_presets'):
            task = self.app.add_task(payload, self.owner['user']['id'])
        self.call(payload={**self.sample(1), 'style':'New preference'})
        frozen = self.app.store.snapshot()['tasks'][task['id']]['teachingMemory']
        self.assertEqual(frozen['style'], 'Explain terms before examples.')
        url = '/v1/tasks/'+task['id']+'/execution-journal'
        self.assertEqual(self.call(url)[1]['teachingMemory'], frozen)
        self.assertEqual(self.call(url, account=self.other)[0], 403)
        self.assertEqual(self.call(url, anonymous=True)[0], 401)

    def test_real_gateway_transport_contains_preferences_and_threads_do_not_share_them(self):
        captured = []
        def transport(req, **kwargs):
            captured.append(json.loads(req.data))
            return io.BytesIO(b'{"choices":[{"message":{"content":"{\\"ok\\":true}"}}]}')
        gateway = ResponsesGateway(self.settings)
        with patch('app.gateway.request.urlopen', side_effect=transport), use_memory(self.sample(), 'S2'):
            self.assertEqual(gateway.respond_json('Translate into English.'), {'ok': True})
        self.assertIn('gradient descent', json.dumps(captured[0]))
        self.assertEqual(apply_current_memory('No memory'), 'No memory')
        barrier = threading.Barrier(2)
        def worker(style):
            with use_memory({**self.sample(), 'style':style, 'glossary':[]}, 'S1'):
                barrier.wait(timeout=5)
                return apply_current_memory('Generate narration.')
        with ThreadPoolExecutor(max_workers=2) as pool:
            a, b = list(pool.map(worker, ['teacher-A', 'teacher-B']))
        self.assertIn('teacher-A', a)
        self.assertNotIn('teacher-B', a)
        self.assertIn('teacher-B', b)
        self.assertNotIn('teacher-A', b)

    def test_failed_stage_resume_keeps_run_history_and_memory_snapshot(self):
        runner = FullPipelineRunner(self.settings)
        task = {'id':'task_fixture', 'mode':'topic', 'targetLanguages':['英语'],
                'teachingMemory': self.sample(), 'outputs':{'s1':{},'s2':{},'s3':{},'s4':{}}}
        runner._run_s5 = Mock(side_effect=ValueError('Fixture compose failure'))
        with self.assertRaisesRegex(ValueError, 'Fixture compose failure'):
            runner.run(task['id'], task, lambda *_:None, start_stage=5)
        runner._run_s5 = Mock(return_value={'languages':{}})
        runner.run(task['id'], task, lambda *_:None, start_stage=5)
        journal = json.loads((runner._task_root(task['id'])/'execution-journal.json').read_text())
        self.assertEqual([run['status'] for run in journal['runs']], ['failed','completed'])
        self.assertEqual(journal['runs'][0]['stages']['S5']['status'], 'failed')
        self.assertEqual(journal['runs'][1]['reusedStages'], ['S1','S2','S3','S4'])
        self.assertEqual(journal['teachingMemory'], task['teachingMemory'])

    def test_parallel_ppt_text_translation_keeps_the_same_teacher_context(self):
        from app.pptx_translation import translate_package
        root = Path(self.directory.name)
        source = root/'source.pptx'
        with zipfile.ZipFile(source, 'w') as package:
            package.writestr('ppt/presentation.xml', '<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><p:sldIdLst><p:sldId id="257" r:id="rId1"/></p:sldIdLst></p:presentation>')
            package.writestr('ppt/_rels/presentation.xml.rels', '<Relationships><Relationship Id="rId1" Target="slides/slide1.xml"/></Relationships>')
            package.writestr('ppt/slides/slide1.xml', '<a:p xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:r><a:t>梯度下降</a:t></a:r></a:p>')
        captured = []
        def respond(prompt, **kwargs):
            captured.append(apply_current_memory(prompt))
            return {'paragraphs': [['gradient descent']]}
        with use_memory(self.sample(), 'S2'):
            translate_package(source, root/'translated.pptx', Mock(settings=None, respond_json=respond), 'English')
        self.assertEqual(len(captured), 1)
        self.assertIn('Explain terms before examples.', captured[0])
        self.assertEqual(apply_current_memory('Outside task'), 'Outside task')


if __name__ == '__main__':
    unittest.main()
