"""Execute Bridge adapter and benchmark gates sequentially on one physical NPU."""
from pathlib import Path
import importlib.metadata as md
import json, os, subprocess, sys, time, traceback
H=Path(__file__).resolve().parent
F=H/'framework'
def save(name,data): (H/'outputs'/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def event(stage,**extra): print(json.dumps(dict(stage=stage,**extra)),flush=True)
packages={}
for name in ['torch','torch-npu','diffusers','transformers','accelerate','safetensors','numpy','einops','Pillow','omegaconf','ftfy','sentencepiece','torchvision','torchaudio','easydict']:
    try: packages[name]=md.version(name)
    except md.PackageNotFoundError: packages[name]=None
record=dict(python_executable=sys.executable,python_version=sys.version,packages=packages,temporary_directory=os.environ['TMPDIR'],ascend_home=os.environ.get('ASCEND_HOME_PATH'),environment_mode='Existing persistent model environment reused without synchronization or installation',fresh_isolated_environment_verified=False)
save('environment.json',record)
assert packages['torch'] in ['2.7.1','2.7.1+cpu']
assert packages['torch-npu']=='2.7.1'
assert Path(os.environ['TMPDIR']).resolve().is_relative_to(Path('/home/ma-user/work'))
event('runtime_verified',python=sys.executable,torch=packages['torch'],torch_npu=packages['torch-npu'])
results=[]
for directory in ['alibaba_pai_easyanimatev3_xl_2_inp_512x512','wan_ai_wan2_2_s2v_14b']:
    adapt=F/'adaptations'/directory
    start=time.time();row=dict(adaptation=directory,started_epoch=start)
    event('benchmark_start',adaptation=directory)
    with (H/'logs'/(directory+'.log')).open('w') as log:
        response=subprocess.run([sys.executable,'accuracy_run.py','--use-pretrained','--max-samples','50'],cwd=adapt,stdout=log,stderr=subprocess.STDOUT)
    row.update(exit_code=response.returncode,wall_seconds=time.time()-start)
    for name,script in [('adaptation_gate','adaptation/scripts/check_adaptation.py'),('benchmark_gate','benchmark/scripts/check_accuracy_run.py')]:
        response=subprocess.run([sys.executable,str(F/script),'--adapt',directory],cwd=F,capture_output=True,text=True)
        (H/'logs'/(directory+'-'+name+'.log')).write_text(response.stdout+response.stderr)
        row[name]=dict(exit_code=response.returncode)
    metrics_files=list(adapt.glob('benchmark_metrics_*pretrained*.json'))
    if metrics_files:
        response=subprocess.run([sys.executable,str(F/'benchmark/scripts/benchmark_tool.py'),'trace','--adaptation',directory,'-j'],cwd=F,capture_output=True,text=True)
        (H/'outputs'/(directory+'-trace-analysis.json')).write_text(response.stdout)
        (H/'logs'/(directory+'-trace-analysis.stderr.log')).write_text(response.stderr)
        row['trace_analysis_exit_code']=response.returncode
    if row['adaptation_gate']['exit_code']==0 and row['benchmark_gate']['exit_code']==0 and metrics_files:
        metrics=json.loads(metrics_files[-1].read_text())
        note=json.dumps(dict(scope=metrics['workload'],num_samples=metrics['num_samples'],metrics_file=metrics_files[-1].name,latency_s=metrics['latency_s'],full_video_pipeline=False,independent_accuracy_evaluation=False))
        # Upstream formal completion invokes file digests and a new environment
        # rebuild. The user's file-digest prohibition takes precedence; retain
        # actual runtime results without invoking or claiming that extra gate.
        row['formal_environment_validation']=dict(executed=False,reason='Upstream validator computes file digests; forbidden by current workspace instructions. Existing persistent environment is reused, not a new isolated installation.')
        for label,args in [('adaptation',['update_adaptation_status','--model_id',metrics['model_id'],'--adaptation_status','in_progress','--adaptation_path','adaptations/'+directory,'--adaptation_notes',note]),('benchmark',['update_benchmark_status','--model_id',metrics['model_id'],'--benchmark_status','in_progress','--notes',note])]:
            response=subprocess.run([sys.executable,str(F/'scripts/board_ops.py'),*args],cwd=F,capture_output=True,text=True)
            (H/'logs'/(directory+'-board-'+label+'.log')).write_text(response.stdout+response.stderr)
            row['board_'+label]=dict(exit_code=response.returncode)
    results.append(row);save('execution.json',results);event('benchmark_finished',**row)
save('execution-complete.json',dict(completed=True,models=results,full_video_pipeline=False,cross_device_numerical_comparison=False))
