"""Bounded single-NPU execution; existing storage and other owners are preserved."""
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
import csv, json, os, shlex, subprocess, sys, tarfile, threading, time

H = Path(__file__).resolve().parent
R = '/home/ma-user/work/npu-migration'
REMOTE = R + '/recovery/' + H.name
for name in ['tmp', 'logs', 'outputs', 'inputs']:
    (H / name).mkdir(exist_ok=True)
os.environ.update(TMPDIR=str(H/'tmp'), TEMP=str(H/'tmp'), TMP=str(H/'tmp'))
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.http.http_config import HttpConfig
from huaweicloudsdkmodelarts.v1 import ModelArtsClient, ShowNotebookRequest, StartNotebookRequest, StopNotebookRequest

PRIVATE_CONFIG = json.loads(Path(os.environ.get('BRIDGE_CLOUD_CONFIG', H/'cloud-config.private.json')).read_text())
IDENTIFIER = PRIVATE_CONFIG['notebook_id']
with Path(PRIVATE_CONFIG['credentials_csv']).expanduser().open(encoding='utf-8-sig') as handle:
    keys = next(csv.DictReader(handle))
config = HttpConfig.get_default_config()
config.timeout = 12
client = ModelArtsClient.new_builder().with_http_config(config).with_credentials(BasicCredentials(keys['Access Key Id'], keys['Secret Access Key'], PRIVATE_CONFIG['project_id'])).with_endpoint('https://modelarts.'+PRIVATE_CONFIG['region']+'.myhuaweicloud.com').build()
LOCK = threading.Lock()
DONE = threading.Event()

def now(): return datetime.now().astimezone().isoformat()
def write(name, data):
    with LOCK:
        p = H/name
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')
def state(): return client.show_notebook(ShowNotebookRequest(id=IDENTIFIER)).to_dict()
def event(stage, **extra):
    row = dict(time=now(), stage=stage, **extra)
    with LOCK:
        with (H/'logs/controller.jsonl').open('a') as f: f.write(json.dumps(row)+'\n')
    print(json.dumps(row), flush=True)
def stop_owned():
    lease_path = H/'lease.json'
    if not lease_path.exists(): return
    lease = json.loads(lease_path.read_text())
    for attempt in range(8):
        try:
            current = state()
            expected = lease.get('platform_lease_updated_at')
            actual = (current.get('lease') or {}).get('update_at')
            if current['status']=='STOPPED':
                lease.update(closed=True, stopped_confirmed_at=now(), stopped_confirmed_epoch=time.time())
                lease['estimated_session_cny']=(lease['stopped_confirmed_epoch']-lease['start_epoch'])*33.968/3600
                write('lease.json', lease)
                event('owned_compute_stopped', estimated_session_cny=lease['estimated_session_cny'])
                return
            if expected is not None and actual!=expected:
                lease.update(closed=True, superseded_by_later_owner=True)
                write('lease.json',lease)
                event('ownership_changed_no_stop')
                return
            if current['status']!='STOPPING':
                client.stop_notebook(StopNotebookRequest(id=IDENTIFIER))
                event('stop_requested')
        except Exception as ex: event('stop_retry', attempt=attempt+1, exception=type(ex).__name__)
        time.sleep(5)
    event('stop_confirmation_incomplete')
def guard(deadline):
    while not DONE.wait(2):
        if time.time()>=deadline:
            event('execution_time_limit_reached')
            stop_owned()
            return
def ssh_args():
    c=json.loads((H/'connection.private.json').read_text())
    return ['ssh','-F','/dev/null','-i',c['key_file'],'-p',str(c['port']),'-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','ConnectTimeout=12','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=2','-o','ControlMaster=no','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile="'+str(H/'known_hosts')+'"','-o','LogLevel=ERROR',c['username']+'@'+c['host']]
def ssh(command, timeout=60, stdin=None):
    return subprocess.run([*ssh_args(),command], stdin=stdin, capture_output=True, timeout=timeout)
def collect():
    command = 'cd '+shlex.quote(REMOTE)+" && tar -czf - --exclude='*.safetensors' --exclude='models' --exclude='.venv' --exclude='__pycache__' --exclude='.git' outputs logs framework/adaptations framework/board.db"
    p=subprocess.run([*ssh_args(),command],capture_output=True,timeout=65)
    (H/'logs/collection-stderr.log').write_bytes(p.stderr)
    if p.returncode: raise RuntimeError('Result collection failed')
    archive=H/'inputs/remote-results.tar.gz';archive.write_bytes(p.stdout)
    with tarfile.open(archive) as f:
        for member in f.getmembers():
            if member.issym() or member.islnk() or not (H/member.name).resolve().is_relative_to(H):
                raise RuntimeError('Unexpected archive member')
        f.extractall(H)
    event('results_collected',archive_bytes=len(p.stdout))
def main():
    if sys.argv[1:]==['collect']:
        collect();return
    if sys.argv[1:]==['stop']:
        stop_owned();return
    prior={'estimated_total_compute_cny':float(PRIVATE_CONFIG.get('prior_estimate_cny',0))}
    if (H/'lease.json').exists():
        previous=json.loads((H/'lease.json').read_text())
        if not previous.get('closed'):raise RuntimeError('An existing trial lease is still active')
        index=len(list(H.glob('lease-attempt*.json')))+1
        (H/'lease.json').rename(H/('lease-attempt'+str(index)+'.json'))
    previous_trial_cost=sum(json.loads(p.read_text()).get('estimated_session_cny',0) for p in H.glob('lease-attempt*.json'))
    prior_cost=prior['estimated_total_compute_cny']+previous_trial_cost
    authorization=json.loads((H/'budget-authorization.json').read_text()) if (H/'budget-authorization.json').exists() else dict(total_budget_cny=50,max_new_lease_seconds=420)
    total_budget=authorization['total_budget_cny']
    remaining=total_budget-prior_cost
    seconds=min(authorization.get('max_new_lease_seconds',420),int((remaining-5)*3600/33.968))
    if seconds < 240:
        raise RuntimeError('The remaining original budget is insufficient')
    current=state()
    if current['status']!='STOPPED': raise RuntimeError('Notebook is owned by another active task')
    started=time.time();deadline=started+seconds
    lease=dict(notebook_id=IDENTIFIER,start_epoch=started,started_at=now(),deadline_epoch=deadline,limit_seconds=seconds,prior_estimated_cny=prior_cost,total_budget_cny=total_budget,closed=False)
    write('lease.json',lease)
    watcher=threading.Thread(target=guard,args=(deadline,),daemon=True)
    acknowledged=False
    try:
        started_response=client.start_notebook(StartNotebookRequest(id=IDENTIFIER,duration=3600000,type='TIMING')).to_dict()
        acknowledged=True
        lease['platform_lease_updated_at']=(started_response.get('lease') or {}).get('update_at')
        write('lease.json',lease)
        watcher.start();event('start_requested',remaining_budget_cny=remaining,limit_seconds=seconds)
        while time.time()<deadline-240:
            current=state()
            if current['status']=='RUNNING': break
            event('startup_state',status=current['status']);time.sleep(8)
        else: raise RuntimeError('Startup consumed the bounded execution window')
        lease['platform_lease_updated_at']=(current.get('lease') or {}).get('update_at');write('lease.json',lease)
        endpoint=next(x['uri'] for x in current['endpoints'] if x['service']=='SSH')
        u=urlparse(endpoint);c=dict(host=u.hostname,port=u.port or 22,username=u.username or 'ma-user',key_file=str(Path(PRIVATE_CONFIG['ssh_key_file']).expanduser()))
        write('connection.private.json',c);(H/'connection.private.json').chmod(0o600)
        scan=subprocess.run(['ssh-keyscan','-T','10','-p',str(c['port']),'-t','rsa,ed25519',c['host']],capture_output=True,timeout=25)
        if not scan.stdout.strip(): raise RuntimeError('SSH host keys unavailable')
        (H/'known_hosts').write_bytes(scan.stdout)
        readiness=ssh('set -e\nfindmnt -no FSTYPE,SOURCE -T /home/ma-user/work\ntest -w /home/ma-user/work\ntest -x '+R+'/envs/npu-base/bin/python\ndf -h /home/ma-user/work\nnpu-smi info',60)
        (H/'logs/remote-readiness.log').write_bytes(readiness.stdout+readiness.stderr)
        if readiness.returncode or readiness.stdout.splitlines()[0].split()[0] not in [b'ext4',b'xfs',b'nfs',b'nfs4']:
            raise RuntimeError('Persistent runtime verification failed')
        event('persistent_runtime_verified')
        with (H/'inputs/framework.tar.gz').open('rb') as data:
            p=ssh('mkdir -p '+shlex.quote(REMOTE)+' && tar -xzf - -C '+shlex.quote(REMOTE),70,stdin=data)
        (H/'logs/upload.log').write_bytes(p.stdout+p.stderr)
        if p.returncode: raise RuntimeError('Framework transfer failed')
        if '--qwen' in sys.argv[1:]:
            from native_qwen_workflow import run as run_qwen_workflow
            run_qwen_workflow(deadline)
            collect()
            return
        remaining_seconds=int(deadline-time.time()-75)
        if remaining_seconds<120: raise RuntimeError('Insufficient bounded execution time after startup')
        command='cd '+shlex.quote(REMOTE)+' && BRIDGE_BENCHMARK_DEADLINE_EPOCH='+str(int(deadline-75))+' timeout '+str(remaining_seconds)+' bash run_remote.sh'
        event('bridge_execution_started',available_seconds=remaining_seconds)
        try:
            p=ssh(command,remaining_seconds+15)
            (H/'logs/remote-driver.log').write_bytes(p.stdout+p.stderr)
            event('bridge_execution_exited',exit_code=p.returncode)
        except subprocess.TimeoutExpired as ex:
            (H/'logs/remote-driver.log').write_bytes((ex.stdout or b'')+(ex.stderr or b''));event('bridge_execution_timeout')
        collect()
    finally:
        DONE.set()
        if acknowledged:stop_owned()

if __name__=='__main__': main()
