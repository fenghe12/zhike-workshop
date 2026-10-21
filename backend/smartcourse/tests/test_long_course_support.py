import json
import socket
import sys
import tempfile
import threading
import time
import types
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from app.narration import prepare_narration
from app.media_checkpoint import reference_version
from app.speech_worker import serve,exchange


class LongCourseTests(unittest.TestCase):
    def test_narration_batches_preserve_all_page_ids(self):
        calls=[]
        class Gateway:
            def respond_json(self,text,**kwargs):
                request=json.loads(text.split('\n',1)[1]);calls.append(len(request['pages']))
                return {'pages':[{'page_id':p['page_id'],'script_text':p['script_text'],'source_issues':[]} for p in request['pages']]}
        source={'task_id':'long-course','language_code':'en','pages':[{'page_id':i,'script_text':'Text '+str(i)} for i in range(1,13)]}
        with tempfile.TemporaryDirectory() as folder:
            out=prepare_narration(source,Gateway(),Path(folder)/'notes.json')
            self.assertEqual(calls,[5,5,2]);self.assertEqual([p['page_id'] for p in json.loads(out.read_text())['pages']],list(range(1,13)))

    def test_reference_content_change_creates_a_new_version(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.wav';source.write_bytes(b'first input')
            first=reference_version(root/'job',source,'voice');self.assertEqual(first,reference_version(root/'job',source,'voice'))
            source.write_bytes(b'second input');self.assertNotEqual(first,reference_version(root/'job',source,'voice'))
            self.assertNotEqual(first,reference_version(root/'other-job',source,'voice'))

    def test_worker_reuses_only_model_and_keeps_request_outputs_distinct(self):
        created=[];calls=[]
        class Model:
            def __init__(self):created.append(self)
            def synthesize(self,text,reference,output,language):
                calls.append((text,reference,output,language));Path(output).write_bytes(text.encode());return 1.0
        with tempfile.TemporaryDirectory(dir='/tmp') as folder,patch.dict(sys.modules,{'cosyvoice_engine':types.SimpleNamespace(CosyVoiceEngine=Model)}):
            root=Path(folder);worker=threading.Thread(target=serve,args=(root,),daemon=True);worker.start()
            deadline=time.monotonic()+3
            while not (root/'worker.sock').exists() and time.monotonic()<deadline:time.sleep(.01)
            first=exchange(root/'worker.sock',{'id':uuid.uuid4().hex,'text':'First','language':'en'})
            second=exchange(root/'worker.sock',{'id':uuid.uuid4().hex,'text':'Second','language':'de'})
            exchange(root/'worker.sock',{'action':'close'});worker.join(3)
            self.assertEqual(len(created),1);self.assertEqual(len(calls),2)
            self.assertNotEqual(first['output'],second['output']);self.assertFalse(worker.is_alive())
            self.assertFalse((root/'worker.sock').exists())


if __name__=='__main__':unittest.main()
