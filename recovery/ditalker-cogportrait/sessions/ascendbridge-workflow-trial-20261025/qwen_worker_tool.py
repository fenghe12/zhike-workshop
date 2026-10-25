"""Native coding-client tool: sequentially switch Qwen, benchmarks, then Qwen."""
from pathlib import Path
import json,shlex,subprocess,sys,time
H=Path(__file__).resolve().parent
sys.path.insert(0,str(H))
import cloud_session as c
from native_qwen_workflow import refresh_archive,remote_service,wait_ready
if sys.argv[1:]!=['execute']:raise SystemExit('Use execute')
lease=json.loads((H/'lease.json').read_text());deadline=lease['deadline_epoch']
if lease.get('closed') or deadline-time.time()<300:raise RuntimeError('Insufficient active lease time; do not start model work')
index=len(list((H/'outputs').glob('qwen-worker-execution-*.json')))+1
remote_service('stop')
print('Task Qwen exited. Executing the two complete pretrained backbones sequentially.',flush=True)
refresh_archive()
with (H/'inputs/framework.tar.gz').open('rb') as data:
    p=c.ssh('tar -xzf - -C '+shlex.quote(c.REMOTE),timeout=90,stdin=data)
if p.returncode:raise RuntimeError('Prepared framework upload failed')
allowed=max(60,min(1200,int(deadline-time.time()-300)))
try:
    p=c.ssh('cd '+shlex.quote(c.REMOTE)+' && BRIDGE_BENCHMARK_DEADLINE_EPOCH='+str(int(deadline-240))+' timeout '+str(allowed)+' bash run_remote.sh',timeout=allowed+15)
    (H/'logs'/('qwen-worker-'+str(index)+'.log')).write_bytes(p.stdout+p.stderr)
    code=p.returncode
except subprocess.TimeoutExpired as ex:
    (H/'logs'/('qwen-worker-'+str(index)+'.log')).write_bytes((ex.stdout or b'')+(ex.stderr or b''));code=124
finally:
    c.collect()
    remote_service('start');wait_ready(deadline)
results=[]
for path in (H/'framework/adaptations').iterdir():
    if not path.is_dir():continue
    status=json.loads((path/'.benchmark-status.json').read_text()) if (path/'.benchmark-status.json').exists() else {}
    metrics=list(path.glob('benchmark_metrics_*pretrained*.json'))
    data=json.loads(metrics[-1].read_text()) if metrics else {}
    results.append(dict(adaptation=path.name,status=status.get('status'),num_samples=data.get('num_samples',status.get('num_samples',0)),latency_s=data.get('latency_s'),peak_memory_mb=data.get('peak_memory_mb'),exception=(status.get('exception') or '')[:700],local_artifact_directory=str(path)))
record=dict(worker_exit_code=code,models=results,Qwen_restarted_after_benchmarks=True,formal_environment_rebuild_executed=False,formal_board_completion=False,formal_completion_limitation='Upstream environment validator calculates file digests, forbidden by current user instructions; actual runtime check results are retained.')
(H/'outputs'/('qwen-worker-execution-'+str(index)+'.json')).write_text(json.dumps(record,ensure_ascii=False,indent=2))
print(json.dumps(record,ensure_ascii=False),flush=True)
