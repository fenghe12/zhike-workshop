"""Run the native Bridge coding client against the existing self-hosted Qwen."""
from pathlib import Path
import json,os,shlex,subprocess,sys,tarfile,time,urllib.request
H=Path(__file__).resolve().parent
F=H/'framework'
BASE='http://127.0.0.1:17823'
MODEL='Qwen3.6-35B-A3B-Bridge'

def request(path,body=None,timeout=20):
    data=json.dumps(body).encode() if body is not None else None
    q=urllib.request.Request(BASE+path,data=data,headers={'content-type':'application/json','anthropic-version':'2023-06-01','x-api-key':'local-qwen'})
    with urllib.request.urlopen(q,timeout=timeout) as response:return json.load(response)
def remote_service(action):
    import cloud_session as c
    p=c.ssh(c.R+'/envs/npu-base/bin/python '+shlex.quote(c.REMOTE+'/qwen_service.py')+' '+action,timeout=65)
    if p.returncode:raise RuntimeError('Task Qwen '+action+' failed: '+p.stderr.decode(errors='replace')[-500:])
    return p.stdout.decode(errors='replace')
def wait_ready(deadline):
    ready_deadline=min(deadline-60,time.time()+360)
    while time.time()<ready_deadline:
        try:
            if request('/health',timeout=3).get('status')=='ok':return
        except Exception:pass
        time.sleep(5)
    raise RuntimeError('Self-hosted Qwen did not become ready within the allowed window')
def refresh_archive():
    p=H/'inputs/framework.tar.gz'
    with tarfile.open(p.with_suffix('.staged'),'w:gz') as archive:
        archive.add(F,arcname='framework',filter=lambda t:None if any(x in Path(t.name).parts for x in ['__pycache__','.venv','.git','models','tmp','torch-cache','compiler-cache','profiling']) else t)
        for name in ['run_remote.sh','run_models.py','run_qwen.sh','qwen_service.py','npu_preflight.py']:archive.add(H/name,arcname=name)
    p.with_suffix('.staged').replace(p)
def run(deadline):
    import cloud_session as c
    command='source '+c.R+'/scripts/persistent-npu-env.sh\nexport TMPDIR='+c.R+'/runtime/b25p TEMP='+c.R+'/runtime/b25p TMP='+c.R+'/runtime/b25p\nmkdir -p "$TMPDIR"\nexport TORCH_DEVICE_BACKEND_AUTOLOAD=0\n'+c.R+'/envs/npu-base/bin/python '+shlex.quote(c.REMOTE+'/npu_preflight.py')
    p=c.ssh('bash -c '+shlex.quote(command),timeout=120)
    (H/'logs/npu-short-temp-preflight.log').write_bytes(p.stdout+p.stderr)
    if p.returncode:raise RuntimeError('Actual short-temp NPU preflight failed; log saved')
    c.event('short_temp_npu_preflight_passed')
    ssh=c.ssh_args()
    tunnel=subprocess.Popen([*ssh[:-1],'-o','ExitOnForwardFailure=yes','-L','127.0.0.1:17823:127.0.0.1:7823','-N',ssh[-1]],stdin=subprocess.DEVNULL,stdout=(H/'logs/qwen-tunnel.log').open('a'),stderr=subprocess.STDOUT)
    try:
        remote_service('start')
        if tunnel.poll() is not None:raise RuntimeError('The owned local forwarding connection failed')
        wait_ready(deadline);c.event('self_hosted_qwen_ready')
        probe=request('/v1/messages',{'model':MODEL,'max_tokens':128,'messages':[{'role':'user','content':'Call the record_ready tool with text ready. No other text.'}],'tools':[{'name':'record_ready','description':'Record a readiness message','input_schema':{'type':'object','properties':{'text':{'type':'string'}},'required':['text']}}],'tool_choice':{'type':'tool','name':'record_ready'}},timeout=120)
        (H/'outputs/qwen-anthropic-tool-probe.json').write_text(json.dumps(probe,ensure_ascii=False,indent=2))
        if not any(x.get('type')=='tool_use' and x.get('name')=='record_ready' for x in probe.get('content',[])):
            raise RuntimeError('Qwen did not return a real Anthropic tool call')
        c.event('qwen_native_tool_call_passed')
        env=os.environ.copy()
        env.pop('ANTHROPIC_AUTH_TOKEN',None)
        env.update(ANTHROPIC_API_KEY='local-qwen',ANTHROPIC_BASE_URL=BASE,ANTHROPIC_MODEL=MODEL,ANTHROPIC_DEFAULT_SONNET_MODEL=MODEL,ANTHROPIC_DEFAULT_OPUS_MODEL=MODEL,ANTHROPIC_DEFAULT_HAIKU_MODEL=MODEL,CLAUDE_CONFIG_DIR=str(H/'qwen-agent'),TMPDIR=str(H.parents[1]/'.runtime/b25'),TEMP=str(H.parents[1]/'.runtime/b25'),TMP=str(H.parents[1]/'.runtime/b25'),XDG_CACHE_HOME=str(H/'cache'),NODE_COMPILE_CACHE=str(H/'cache/node'),DISABLE_AUTOUPDATER='1',CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1',BASH_DEFAULT_TIMEOUT_MS='600000',BASH_MAX_TIMEOUT_MS='600000',CLAUDE_CODE_MAX_OUTPUT_TOKENS='4096',API_TIMEOUT_MS='180000')
        Path(env['TMPDIR']).mkdir(parents=True,exist_ok=True)
        system='You are the AscendBridge adapter and benchmark worker, using the existing Bridge role and diffusion workflow. Follow the supplied task exactly. Use real tools. Never claim NPU success without actual result files. Do not calculate file hashes or access credentials. All changes are restricted to the current framework and its two adaptations. Do not start/stop notebooks or other tasks. One physical NPU is used sequentially. Do not create teams in this bounded single-worker continuation.'
        task=(H/'qwen-task.txt').read_text().replace('{{SESSION_ROOT}}',str(H))
        cmd=['claude','--bare','-p','--setting-sources','','--strict-mcp-config','--mcp-config','{"mcpServers":{}}','--model',MODEL,'--system-prompt',system,'--tools','Write,Bash','--allowedTools','Write,Bash','--permission-mode','dontAsk','--no-session-persistence','--output-format','stream-json','--verbose',task]
        c.event('native_bridge_qwen_client_started')
        with (H/'logs/native-qwen-client.jsonl').open('w') as log:
            result=subprocess.run(cmd,cwd=F,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=max(60,int(deadline-time.time()-90)))
        events=[]
        for line in (H/'logs/native-qwen-client.jsonl').read_text(errors='replace').splitlines():
            try:events.append(json.loads(line))
            except ValueError:pass
        tools=[block for event in events for block in (event.get('message') or {}).get('content',[]) if isinstance(block,dict) and block.get('type')=='tool_use']
        native_status=dict(provider='self-hosted Qwen3.6-35B-A3B Q8_0',anthropic_tool_probe_passed=True,exit_code=result.returncode,actual_client_tool_calls=[dict(name=t.get('name'),input=t.get('input')) for t in tools],worker_execution_records=len(list((H/'outputs').glob('qwen-worker-execution-*.json'))),plan_file_exists=(F/'qwen-migration-plan.json').exists(),review_file_exists=(F/'qwen-final-review.json').exists(),external_Kimi_used=False)
        (H/'outputs/qwen-native-status.json').write_text(json.dumps(native_status,ensure_ascii=False,indent=2))
        c.event('native_bridge_qwen_client_exited',exit_code=result.returncode)
        return result.returncode
    finally:
        try:remote_service('stop')
        except Exception as ex:c.event('qwen_service_stop_issue',exception=type(ex).__name__)
        command=subprocess.run(['ps','-p',str(tunnel.pid),'-o','pid=,ppid=,command='],capture_output=True,text=True).stdout
        (H/'logs/qwen-tunnel-stop-process-check.txt').write_text(command)
        if tunnel.poll() is None and '17823:127.0.0.1:7823' in command:
            tunnel.terminate();tunnel.wait(timeout=15)

