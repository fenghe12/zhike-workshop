"""A voice-model session belonging to one pipeline invocation and reference file."""
import json
import os
import shlex
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from .remote_media import _connection


class RemoteSpeechSession:
    def __init__(self,reference):
        self.reference=Path(reference);self.reference_bytes=self.reference.read_bytes()
        self.identifier=uuid.uuid4().hex
        base=os.environ.get('SMARTCOURSE_REMOTE_ROOT','/home/ma-user/work/smartcourse')
        self.root=base+'/mooc-sessions/'+self.identifier
        self.base=base;self.started=False
        options,port,host=_connection();self.host=host
        self.ssh=['ssh',*options,'-p',str(port),host]
        self.scp=['scp',*options,'-P',str(port)]
        self.python=os.environ.get('SMARTCOURSE_REMOTE_PYTHON','/home/ma-user/anaconda3/envs/MindSpore/bin/python')

    def _worker_command(self,*arguments):
        bootstrap=os.environ.get('SMARTCOURSE_REMOTE_LAUNCHER_PYTHON',self.python)
        environment=os.environ.get('SMARTCOURSE_REMOTE_ENV_SCRIPT')
        prefix=('source '+shlex.quote(environment)+' && ') if environment else ''
        script=prefix+'NPU_MIGRATE=0 '+shlex.join([bootstrap,self.root+'/speech_worker.py',*arguments])
        return [*self.ssh,'bash -c '+shlex.quote(script)]

    def start(self):
        package=Path(__file__).resolve().parents[1]
        subprocess.run([*self.ssh,shlex.join(['mkdir','-p',self.root+'/requests'])],check=True,capture_output=True,timeout=45)
        subprocess.run([*self.scp,str(package/'agents/cosyvoice_engine.py'),str(package/'app/speech_worker.py'),self.host+':'+self.root+'/'],check=True,capture_output=True,timeout=120)
        subprocess.run([*self.scp,str(self.reference),self.host+':'+self.root+'/reference.wav'],check=True,capture_output=True,timeout=120)
        env={'PYTHONPATH':self.base+'/envs/cosyvoice3-runtime:'+self.base+'/envs/xtts-runtime:'+self.base+'/env',
             'SMARTCOURSE_COSYVOICE_ROOT':os.environ['SMARTCOURSE_REMOTE_COSYVOICE_ROOT'],
             'SMARTCOURSE_COSYVOICE_MODEL':self.base+'/shared/models/Fun-CosyVoice3-0.5B-2512','SMARTCOURSE_REMOTE_MEDIA':'0'}
        arguments=[self.python,self.root+'/speech_worker.py','--serve',self.root]
        launcher='import os,subprocess; env=os.environ.copy(); env.update('+repr(env)+'); log=open('+repr(self.root+'/service.log')+',"a"); child=subprocess.Popen('+repr(arguments)+',env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,close_fds=True); print(child.pid)'
        bootstrap=os.environ.get('SMARTCOURSE_REMOTE_LAUNCHER_PYTHON',self.python)
        environment=os.environ.get('SMARTCOURSE_REMOTE_ENV_SCRIPT')
        prefix=('source '+shlex.quote(environment)+' && ') if environment else ''
        script=prefix+'NPU_MIGRATE=0 '+shlex.join([bootstrap,'-c',launcher])
        subprocess.run([*self.ssh,'bash -c '+shlex.quote(script)],check=True,capture_output=True,timeout=60)
        for attempt in range(90):
            result=subprocess.run([*self.ssh,shlex.join(['test','-S',self.root+'/worker.sock'])],capture_output=True,timeout=20)
            if result.returncode==0:self.started=True;return
            time.sleep(2)
        raise RuntimeError('语音模型服务未能启动')

    def synthesize(self,text,output,language):
        _connection()
        if not self.started:self.start()
        else:
            ping=subprocess.run(self._worker_command('--socket',self.root+'/worker.sock','--ping'),capture_output=True,timeout=30)
            if ping.returncode==255:raise RuntimeError('媒体服务 SSH 连接失败')
            if ping.returncode:self.start()
        output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);identifier=uuid.uuid4().hex
        payload={'id':identifier,'text':text,'language':language}
        if language == 'ja' and os.environ.get('SMARTCOURSE_JAPANESE_GUIDE_MODELS'):
            from .japanese_guide import prepare
            guide=prepare(text,output.with_name(output.stem+'.japanese-guide.wav'))
            remote_guide=self.root+'/requests/'+identifier+'.guide.wav'
            remote_timing=self.root+'/requests/'+identifier+'.guide.timing.json'
            subprocess.run([*self.scp,str(guide),self.host+':'+remote_guide],check=True,capture_output=True,timeout=180)
            subprocess.run([*self.scp,str(guide.with_suffix('.timing.json')),self.host+':'+remote_timing],check=True,capture_output=True,timeout=120)
            payload.update(sourceGuide=remote_guide,sourceGuideTiming=remote_timing)
        with tempfile.TemporaryDirectory(prefix='speech-request-') as temporary:
            request=Path(temporary)/'request.json';request.write_text(json.dumps(payload,ensure_ascii=False))
            remote_request=self.root+'/requests/'+identifier+'.json'
            subprocess.run([*self.scp,str(request),self.host+':'+remote_request],check=True,capture_output=True,timeout=120)
            call=subprocess.run(self._worker_command('--socket',self.root+'/worker.sock','--request',remote_request),capture_output=True,text=True,timeout=950)
            output.with_suffix('.remote.log').write_text(call.stdout+'\n'+call.stderr)
            if call.returncode:raise RuntimeError('语音模型请求未完成，任务日志已保存')
            response=json.loads(call.stdout)
            if not response.get('ok'):raise RuntimeError(response.get('error','语音模型请求失败'))
            remote=self.root+'/outputs/'+identifier
            pending=output.with_name('.'+output.name+'.download')
            subprocess.run([*self.scp,self.host+':'+remote+'/output.wav',str(pending)],check=True,capture_output=True,timeout=180);pending.replace(output)
            timing=output.with_suffix('.timing.json');pending=timing.with_suffix('.pending.json')
            subprocess.run([*self.scp,self.host+':'+remote+'/output.timing.json',str(pending)],check=True,capture_output=True,timeout=120);pending.replace(timing)
            output.with_suffix('.remote.json').write_text(json.dumps({'session':self.identifier,'remoteDirectory':remote},indent=2))
            return float(response['duration'])

    def close(self):
        if self.started:
            try:subprocess.run(self._worker_command('--socket',self.root+'/worker.sock','--close'),capture_output=True,timeout=30)
            except (subprocess.SubprocessError,OSError):pass
            finally:self.started=False
