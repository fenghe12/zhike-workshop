"""Manage only this task's uniquely named local Qwen process on the notebook."""
from pathlib import Path
import json,os,signal,subprocess,sys,time
H=Path(__file__).resolve().parent
for name in ['outputs','logs']:(H/name).mkdir(exist_ok=True)
pidfile=H/'outputs/qwen-service.pid'
def inspect(pid):
    p=subprocess.run(['ps','-p',str(pid),'-o','pid=,ppid=,args='],capture_output=True,text=True)
    return p.stdout.strip()
if sys.argv[1]=='start':
    if pidfile.exists():
        pid=int(pidfile.read_text());command=inspect(pid)
        if 'Qwen3.6-35B-A3B-Bridge' in command:
            print(json.dumps(dict(already_running=True,pid=pid)));raise SystemExit
    model=Path('/home/ma-user/work/npu-migration/checkpoints/course/qwen3.6-35b-a3b-gguf/Qwen3.6-35B-A3B-Q8_0.gguf')
    assert model.is_file() and os.access(model,os.R_OK)
    with (H/'logs/qwen-server.log').open('a') as log:
        p=subprocess.Popen(['bash',str(H/'run_qwen.sh')],stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    pidfile.write_text(str(p.pid));print(json.dumps(dict(started=True,pid=p.pid)),flush=True)
elif sys.argv[1]=='stop':
    if not pidfile.exists():raise SystemExit
    pid=int(pidfile.read_text());command=inspect(pid)
    if command and 'Qwen3.6-35B-A3B-Bridge' not in command and str(H/'run_qwen.sh') not in command:
        raise RuntimeError('PID does not belong to this task Qwen service')
    (H/'logs/qwen-stop-process-check.txt').write_text(command+'\n')
    if command:os.kill(pid,signal.SIGTERM)
    for _ in range(40):
        current=inspect(pid)
        if not current or '<defunct>' in current:break
        time.sleep(1)
    else:raise RuntimeError('Qwen process has not exited; do not start another NPU workload')
    print(json.dumps(dict(stopped=True,pid=pid)),flush=True)
