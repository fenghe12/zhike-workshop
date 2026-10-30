"""Switch only owned model services on a persistent single-device worker."""
from pathlib import Path
import fcntl, json, os, signal, subprocess, sys, time, urllib.request

ROOT=Path('/home/ma-user/work/smartcourse/services')
RUNTIME=Path('/home/ma-user/work/npu-migration')
ROOT.mkdir(parents=True,exist_ok=True)
PID=ROOT/'deeppresenter.pid'
RESUME=ROOT/'qwen-resume-required.json'
OPENER=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def command(pid):
    try:
        state=Path('/proc',str(pid),'stat').read_text().split(') ',1)[1].split()[0]
        if state=='Z':return ''
        return Path('/proc',str(pid),'cmdline').read_bytes().replace(b'\0',b' ').decode()
    except (OSError,ValueError,IndexError):
        return ''

def stop_owned(pid,expected):
    current=command(pid)
    if not current:return
    if expected not in current:raise RuntimeError('Unexpected model process identity')
    inspected=subprocess.check_output(['ps','-p',str(pid),'-o','pid=,ppid=,args='],text=True)
    with (ROOT/'model-lifecycle.log').open('a') as log:log.write(inspected)
    os.kill(pid,signal.SIGTERM)
    for _ in range(120):
        if not command(pid):return
        time.sleep(.25)
    raise RuntimeError('Owned model did not stop')

def qwen_pids():
    executable=str(RUNTIME/'repos/llama.cpp/build-cann/bin/llama-server')
    return [int(p.name) for p in Path('/proc').iterdir() if p.name.isdigit()
            and executable in command(p.name) and 'Qwen3.6-35B-A3B' in command(p.name)]

def presenter_pid():
    if not PID.is_file():return None
    try:pid=int(PID.read_text())
    except ValueError:return None
    value=command(pid)
    if not value:return None
    if 'deeppresenter_server:app' not in value:raise RuntimeError('Unexpected presenter process')
    return pid

def health(url,key):
    try:
        with OPENER.open(url,timeout=3) as response:
            return json.load(response).get(key)
    except (OSError,ValueError):
        return None

def pause_qwen():
    pids=qwen_pids()
    if pids:
        RESUME.write_text(json.dumps({'restart':True}))
        for pid in pids:stop_owned(pid,str(RUNTIME/'repos/llama.cpp/build-cann/bin/llama-server'))

def resume_qwen():
    if not RESUME.exists():return
    work=ROOT/'qwen'
    for name in ['tmp','cache','logs']:(work/name).mkdir(parents=True,exist_ok=True)
    if not qwen_pids():
        env=os.environ.copy()
        env.update({key:str(work/'tmp') for key in ['TMPDIR','TEMP','TMP']})
        with (work/'logs/server.log').open('a') as log:
            subprocess.Popen(['bash',str(RUNTIME/'scripts/start_qwen36_service.sh')],env=env,
                stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    for _ in range(160):
        if health('http://127.0.0.1:7812/health','status')=='ok':
            RESUME.unlink(missing_ok=True);return
        time.sleep(2)
    raise RuntimeError('Qwen did not return to ready status')

def start_presenter():
    pid=presenter_pid()
    if pid is None:
        pause_qwen()
        work=ROOT/'deeppresenter'
        for name in ['tmp','cache','logs']:(work/name).mkdir(parents=True,exist_ok=True)
        env=os.environ.copy()
        env.update({key:str(work/'tmp') for key in ['TMPDIR','TEMP','TMP']})
        env.update(PYTHONPATH=str(RUNTIME/'envs/deeppresenter-py311')+':'+env.get('PYTHONPATH',''),
                   NPU_MIGRATE='0',XDG_CACHE_HOME=str(work/'cache'),PYTHONDONTWRITEBYTECODE='1')
        with (work/'logs/server.log').open('a') as log:
            child=subprocess.Popen([str(RUNTIME/'envs/npu-base/bin/python'),'-m','uvicorn','--app-dir',
                str(ROOT),'deeppresenter_server:app','--host','127.0.0.1','--port','7811'],
                env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
        PID.write_text(str(child.pid))
    for _ in range(240):
        if presenter_pid() is None:raise RuntimeError('Presenter process exited')
        if health('http://127.0.0.1:7811/health','ready'):
            print(json.dumps({'ready':True,'model':'DeepPresenter-9B'}));return
        time.sleep(2)
    raise RuntimeError('Presenter startup timed out')

def stop_presenter():
    pid=presenter_pid()
    if pid:stop_owned(pid,'deeppresenter_server:app')
    PID.unlink(missing_ok=True)
    resume_qwen()
    print(json.dumps({'stopped':True,'qwenRestored':bool(qwen_pids())}))

if __name__=='__main__':
    with (ROOT/'deeppresenter-control.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if sys.argv[1]=='start':
            try:start_presenter()
            except Exception:
                pid=presenter_pid()
                if pid:stop_owned(pid,'deeppresenter_server:app')
                PID.unlink(missing_ok=True);resume_qwen();raise
        elif sys.argv[1]=='stop':stop_presenter()
        else:raise RuntimeError('Unsupported model action')
