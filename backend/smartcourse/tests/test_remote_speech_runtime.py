import ast
import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.remote_speech import RemoteSpeechSession
from app.speech_worker import configure_session_paths


class RemoteSpeechRuntimeTests(unittest.TestCase):
    def test_worker_restores_session_paths_after_a_runtime_wrapper(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            old=tempfile.tempdir
            try:
                configure_session_paths(directory)
                self.assertEqual(tempfile.gettempdir(),str(Path(directory)/'tmp'))
                self.assertTrue(Path(os.environ['XDG_CACHE_HOME']).is_dir())
            finally:
                tempfile.tempdir=old

    def test_worker_receives_pacing_module_and_persistent_runtime_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            reference=root/'voice.wav';reference.write_bytes(b'voice fixture')
            env={'SMARTCOURSE_REMOTE_ROOT':str(root/'remote'),
                 'SMARTCOURSE_REMOTE_COSYVOICE_ROOT':str(root/'cosyvoice'),
                 'SMARTCOURSE_REMOTE_PYTHON':'/persistent/env/bin/python'}
            with patch.dict(os.environ,env), patch('app.remote_speech._connection',return_value=([],22,'fixture')):
                session=RemoteSpeechSession(reference)
            calls=[]
            def run(command,**kwargs):
                calls.append(command)
                return SimpleNamespace(returncode=0,stdout='123',stderr='')
            with patch.dict(os.environ,env), patch('app.remote_speech.subprocess.run',side_effect=run):
                session.start()
            module_copy=next(call for call in calls if any(str(v).endswith('/app/speech_pacing.py') for v in call))
            self.assertIn(str(Path(__file__).parents[1]/'app/config.py'),module_copy)
            self.assertEqual(module_copy[-1],'fixture:'+session.root+'/app/')
            launcher=next(call[-1] for call in calls if 'subprocess.Popen' in call[-1])
            outer=shlex.split(launcher)
            script=shlex.split(outer[-1])
            tree=ast.parse(script[script.index('-c')+1])
            update=next(node for node in ast.walk(tree) if isinstance(node,ast.Call)
                        and isinstance(node.func,ast.Attribute) and node.func.attr=='update')
            environment=ast.literal_eval(update.args[0])
            self.assertEqual(environment['PYTHONPATH'].split(':')[0],session.root)
            for key in ['TMPDIR','TMP','TEMP','XDG_CACHE_HOME','TORCH_EXTENSIONS_DIR']:
                self.assertTrue(environment[key].startswith(str(root/'remote')),key)
            self.assertEqual(environment['SMARTCOURSE_REMOTE_MEDIA'],'0')
            self.assertTrue(session.started)


if __name__=='__main__':unittest.main()
