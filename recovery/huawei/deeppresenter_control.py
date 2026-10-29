from pathlib import Path
import fcntl,json,os,signal,subprocess,sys,time,urllib.request
ROOT=Path('/home/ma-user/work/smartcourse/services');ROOT.mkdir(parents=True,exist_ok=True)
PID=ROOT/'deeppresenter.pid'
def running():
 if not PID.is_file():return None
 try:
  pid=int(PID.read_text());command=Path('/proc',str(pid),'cmdline').read_bytes().replace(b'\0',b' ').decode()
 except (OSError,ValueError):return None
 if not command.strip():return None
 if 'uvicorn' not in command or 'deeppresenter_server:app' not in command:raise RuntimeError('Unexpected model service process')
 return pid
with (ROOT/'deeppresenter-control.lock').open('a') as lock:
 fcntl.flock(lock,fcntl.LOCK_EX)
 action=sys.argv[1];pid=running()
 if action=='start':
  if pid is None:
   r=Path('/home/ma-user/work/npu-migration');work=ROOT/'deeppresenter';work.mkdir(exist_ok=True)
   for name in ('tmp','cache','logs'):(work/name).mkdir(exist_ok=True)
   env=os.environ.copy();env.update({key:str(work/'tmp') for key in ('TMPDIR','TEMP','TMP')})
   env.update(PYTHONPATH=str(r/'envs/deeppresenter-py311')+':'+env.get('PYTHONPATH',''),NPU_MIGRATE='0',XDG_CACHE_HOME=str(work/'cache'),PYTHONDONTWRITEBYTECODE='1')
   with (work/'logs/server.log').open('a') as stream:
    child=subprocess.Popen([str(r/'envs/npu-base/bin/python'),'-m','uvicorn','--app-dir',str(ROOT),'deeppresenter_server:app','--host','127.0.0.1','--port','7811'],env=env,stdin=subprocess.DEVNULL,stdout=stream,stderr=stream,start_new_session=True)
   PID.write_text(str(child.pid));pid=child.pid
  opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
  for _ in range(240):
   if running() is None:raise RuntimeError('Model process exited; inspect persistent model log')
   try:
    with opener.open('http://127.0.0.1:7811/health',timeout=2) as response:
     if json.load(response).get('ready'):print(json.dumps({'ready':True,'model':'DeepPresenter-9B'}));break
   except OSError:pass
   time.sleep(2)
  else:raise RuntimeError('Model did not become ready before startup limit')
 elif action=='stop':
  if pid is not None:
   os.kill(pid,signal.SIGTERM)
   for _ in range(40):
    if running() is None:break
    time.sleep(.5)
   else:raise RuntimeError('Model process did not stop')
  PID.unlink(missing_ok=True);print(json.dumps({'stopped':True}))
 else:raise RuntimeError('Unsupported model action')
