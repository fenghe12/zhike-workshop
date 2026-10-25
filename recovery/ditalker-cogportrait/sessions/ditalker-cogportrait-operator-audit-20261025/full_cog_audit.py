"""Paired fixed-noise losses across all 50 cached cases; full frozen Wan backbone."""
import os,sys,io,json,time,gc,statistics
from pathlib import Path
H=Path(os.environ['AUDIT_SESSION']);DATA=H.parent/'ditalker-cogportrait-50hdtf-200steps-20261025'
os.environ['CUSTOM_TRAINING_SESSION']=str(DATA);sys.path.insert(0,str(DATA))
import train_added_components as training
import torch,requests
from wan_training_adapter import prediction
torch.backends.mha.set_fastpath_enabled(False)
OUT=H/'outputs/cog';OUT.mkdir(exist_ok=True)
model,details=training.make_cog();params={n:p for n,p in model.named_parameters() if p.requires_grad};model.eval()
plan=json.loads((H/'checkpoint-plans/read.private.json').read_text())['cogportrait']
response=requests.get(plan['read_url'],timeout=90);assert response.status_code==200 and len(response.content)==plan['bytes']
state=torch.load(io.BytesIO(response.content),map_location='cpu',weights_only=False);assert state['step']==100
trained=state['added_state'];assert set(trained)==set(params)
rows=[]
def save():
    (OUT/'fixed-losses.json').write_text(json.dumps(dict(protocol=dict(cases=50,split='same_training_50',sigma=.5,seed=6000,frames=16,resolution=[512,512],base='complete released Wan2.2 S2V',compared='identical noise/sample, newly added pose Conv3d initial-zero versus saved-step100'),rows=rows),indent=2)+'\n')
for i,row in enumerate(training.rows):
    sample=torch.load(DATA/'inputs/cogportrait'/(row['id']+'.pt'),map_location='cpu',weights_only=False)
    torch.manual_seed(6000+i);torch.npu.manual_seed(6000+i)
    target_latent=sample['latents'].to('npu').float();noise=torch.randn_like(target_latent);target=noise-target_latent
    values={};torch.npu.synchronize();before=time.perf_counter()
    for variant in ['initialzero','step100']:
        with torch.no_grad():
            for n,p in params.items():p.zero_() if variant=='initialzero' else p.copy_(trained[n].to(p.device))
            output=prediction(model,sample,noise,sigma=.5)
            values[variant]=float(torch.nn.functional.mse_loss(output.float(),target).cpu())
    torch.npu.synchronize();values.update(sample=row['id'],seconds=time.perf_counter()-before)
    rows.append(values);save();print(json.dumps(dict(completed=i+1,total=50,**values)),flush=True)
    del sample,target,target_latent,noise,output
# Verify the actual new branch through a full training backward and a real diagnostic update.
model.train();sample=torch.load(DATA/'inputs/cogportrait'/(training.rows[0]['id']+'.pt'),map_location='cpu',weights_only=False)
torch.manual_seed(7000);torch.npu.manual_seed(7000);torch.npu.reset_peak_memory_stats()
optimizer=torch.optim.AdamW(params.values(),lr=2e-5,foreach=False);before_params={n:p.detach().cpu().clone() for n,p in params.items()}
torch.npu.synchronize();before=time.perf_counter();loss,parts=training.cog_loss(model,training.rows[0],sample,101);torch.npu.synchronize();forward=time.perf_counter();loss.backward();torch.npu.synchronize();backward=time.perf_counter()
grads={n:dict(norm=float(p.grad.float().norm().cpu()),finite=bool(torch.isfinite(p.grad).all())) for n,p in params.items()}
torch.nn.utils.clip_grad_norm_(list(params.values()),1.,foreach=False,error_if_nonfinite=True);optimizer.step();torch.npu.synchronize();updated=time.perf_counter()
diagnostic=dict(loss=float(loss.detach().cpu()),loss_terms=parts,forward_seconds=forward-before,backward_seconds=backward-forward,update_seconds=updated-backward,gradient_by_tensor=grads,parameter_delta_norms={n:float((p.detach().cpu()-before_params[n]).norm()) for n,p in params.items()},peak_allocated_bytes=torch.npu.max_memory_allocated(),source_checkpoint_unchanged=True,extra_step_saved_as_training_result=False)
summary=dict(initialzero_mean=statistics.mean(r['initialzero'] for r in rows),step100_mean=statistics.mean(r['step100'] for r in rows),improved_cases=sum(r['step100']<r['initialzero'] for r in rows),cases=50,training_replay=diagnostic,completed=True,hardware=torch.npu.get_device_name(0),scope='Pose branch only; no agent planner, no KTO')
summary['relative_mean_change_percent']=(summary['step100_mean']/summary['initialzero_mean']-1)*100
(OUT/'diagnosis.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
