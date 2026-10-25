"""Reproduce the cached long AF_UNIX path, then verify the short-path correction."""
from pathlib import Path
import json,multiprocessing,os,subprocess,sys,tempfile
H=Path(__file__).resolve().parent
if len(sys.argv)>1:
    mode=sys.argv[1]
    long=H/'runtime/reproduction-long-persistent-temporary-directory'
    short=H.parents[1]/'.runtime/b25'
    for path in [long,short]:path.mkdir(parents=True,exist_ok=True)
    os.environ['TMPDIR']=str(long);tempfile.tempdir=None
    cached=tempfile.gettempdir()
    os.environ.update(TMPDIR=str(short),TEMP=str(short),TMP=str(short))
    if mode=='clear_cache':tempfile.tempdir=str(short)
    record=dict(mode=mode,cached_before=cached,effective_tempdir=tempfile.gettempdir())
    try:
        with multiprocessing.get_context('fork').Manager() as manager:
            data=manager.dict();data['working']=True;record['manager_communication_passed']=data['working']
    except Exception as ex:record.update(manager_communication_passed=False,exception_type=type(ex).__name__)
    print(json.dumps(record),flush=True)
else:
    rows=[]
    for mode in ['env_only','clear_cache']:
        p=subprocess.run([sys.executable,__file__,mode],capture_output=True,text=True,timeout=20)
        (H/'logs'/('tempdir-reproduction-'+mode+'.log')).write_text(p.stdout+p.stderr)
        rows.append(json.loads(p.stdout.strip().splitlines()[-1]))
    assert not rows[0]['manager_communication_passed']
    assert rows[1]['manager_communication_passed']
    result=dict(local_process_communication_reproduction=True,real_NPU_retest_after_final_fix=False,cases=rows)
    (H/'outputs/tempdir-correction-verification.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result),flush=True)
