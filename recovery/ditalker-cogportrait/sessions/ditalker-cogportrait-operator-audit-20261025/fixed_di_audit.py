"""Preserve original data, repair only condition pixels, and log native loss components."""
import os,sys,io,json,inspect,textwrap,time,gc,statistics,subprocess
from pathlib import Path
H=Path(os.environ['AUDIT_SESSION']);DATA=H.parent/'ditalker-cogportrait-50hdtf-200steps-20261025';BASE=H.parent/'easyanimate-wans2v-training-3h-20261024'
os.environ['CUSTOM_TRAINING_SESSION']=str(DATA);sys.path[:0]=[str(DATA),str(BASE/'source/EasyAnimate')]
os.environ['DITALKER_ALLOW_RECORDED_MASK_CACHE']='1'
import train_added_components as training
import torch,numpy as np,requests
from easyanimate.models import AutoencoderKLMagvit
from ditalker.utils import gaussian_diffusion as gd
torch.backends.mha.set_fastpath_enabled(False)
OUT=H/'outputs/di-fixed';OUT.mkdir(exist_ok=True);CONDITIONS=H/'inputs/di-native-mask';CONDITIONS.mkdir(exist_ok=True)
root=BASE/'models/EasyAnimateV3-XL-2-InP-512x512'
vae=AutoencoderKLMagvit.from_pretrained(str(root),subfolder='vae',torch_dtype=torch.float32).to('npu').eval().requires_grad_(False)
for i,row in enumerate(training.rows):
    dest=CONDITIONS/(row['id']+'.pt')
    if dest.exists():continue
    raw=subprocess.run([str(H.parents[1]/'toolchains/ffmpeg/bin/ffmpeg'),'-v','error','-i',str(DATA/row['file']),'-vf','crop=min(iw\\,ih):min(iw\\,ih),scale=512:512','-frames:v','64','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True).stdout
    video=torch.from_numpy(np.frombuffer(raw,np.uint8).reshape(64,512,512,3).copy()).permute(3,0,1,2).float()[None,:,::4].to('npu')/127.5-1
    masked=torch.full_like(video,-1);masked[:,:,:1]=video[:,:,:1]
    old=torch.load(DATA/'inputs/ditalker'/(row['id']+'.pt'),map_location='cpu',weights_only=False)
    with torch.no_grad(),torch.autocast('npu',dtype=torch.bfloat16):masked_latent=vae.encode(masked).latent_dist.mode()*vae.config.scaling_factor
    torch.save(dict(inpaint_latents=torch.cat([old['inpaint_latents'][:,:4],masked_latent.cpu().bfloat16()],dim=1),preprocessing_version='native_mask_unknown_minus_one_v1',original_cache_unchanged=True),dest)
    print(json.dumps(dict(stage='native masked condition',completed=i+1,total=50)),flush=True)
del vae
for variable in ['old','video','masked','masked_latent','raw']:
    globals().pop(variable,None)
gc.collect();torch.npu.empty_cache()
# Add explicit scalar component logging without changing native arithmetic or weights.
source=textwrap.dedent(inspect.getsource(gd.GaussianDiffusion.training_losses))
markers={
 'loss = (target - output) ** 2':'loss = (target - output) ** 2\n        terms["noise_mse"] = mean_flat(loss)\n        terms["training_timestep"] = t.float()',
 'loss += region_loss_weight * (target_eye - output_eye) ** 2':'loss += region_loss_weight * (target_eye - output_eye) ** 2\n            terms["eye_mse_weighted"] = mean_flat(region_loss_weight * (target_eye - output_eye) ** 2)',
 'loss += repa_weight * proj_loss':'loss += repa_weight * proj_loss\n            terms["repa_negative_cosine"] = proj_loss\n            terms["repa_weighted"] = repa_weight * proj_loss',
}
for before,after in markers.items():
    logged_field={'loss = (target - output) ** 2':'noise_mse','loss += region_loss_weight * (target_eye - output_eye) ** 2':'eye_mse_weighted','loss += repa_weight * proj_loss':'repa_negative_cosine'}[before]
    if 'terms["'+logged_field+'"]' not in source:
        assert source.count(before)==1,before;source=source.replace(before,after)
namespace=dict(gd.__dict__);exec(compile(source,'<native-loss-scalar-logging>','exec'),namespace)
gd.GaussianDiffusion.training_losses=namespace['training_losses']
model,details=training.make_ditalker();params={n:p for n,p in model.named_parameters() if p.requires_grad}
plan=json.loads((H/'checkpoint-plans/read.private.json').read_text())['ditalker'];buffer=io.BytesIO()
with requests.get(plan['read_url'],stream=True,timeout=(30,180)) as r:
    assert r.status_code==200
    for chunk in r.iter_content(8*1024**2):buffer.write(chunk)
assert buffer.tell()==plan['bytes'];buffer.seek(0);payload=torch.load(buffer,map_location='cpu',weights_only=False);buffer.close()
nonzero={n:p for n,p in payload['added_state'].items() if bool(p.any())}
with torch.no_grad():
    for p in params.values():p.zero_()
    buffers=dict(model.named_buffers())
    for n,v in payload.get('added_buffers',{}).items():buffers[n].copy_(v.to('npu'))
del payload;gc.collect();torch.npu.empty_cache();model.eval()
rows=[]
for i,row in enumerate(training.rows):
    sample=torch.load(DATA/'inputs/ditalker'/(row['id']+'.pt'),map_location='cpu',weights_only=False)
    original=sample['inpaint_latents'];native=torch.load(CONDITIONS/(row['id']+'.pt'),map_location='cpu',weights_only=False)['inpaint_latents']
    rec=dict(sample=row['id'],seed=9000+i)
    for condition in ['original','native']:
        sample['inpaint_latents']=original if condition=='original' else native
        for variant in ['initialzero','step100']:
            with torch.no_grad():
                for n,v in nonzero.items():params[n].zero_() if variant=='initialzero' else params[n].copy_(v.to('npu'))
                torch.manual_seed(9000+i);torch.npu.manual_seed(9000+i)
                value,terms=training.di_loss(model,row,sample,i+1)
                residual=terms['loss']-sum(terms[k] for k in ['noise_mse','eye_mse_weighted','repa_weighted','vb'])
                assert abs(residual)<2e-5,(residual,terms)
            rec[condition+'_'+variant]=dict(loss=float(value.cpu()),components=terms,decomposition_residual=residual)
    rows.append(rec);(OUT/'fixed-losses.json').write_text(json.dumps(dict(protocol=dict(cases=50,split='same_training_50',paired_noise=True,seed=9000,all_added_parameters_initial_zero=True,native_loss_arithmetic_preserved=True,original_cache_unchanged=True),rows=rows),indent=2)+'\n')
    print(json.dumps(dict(stage='paired native losses',completed=i+1,total=50)),flush=True)
summary={}
for condition in ['original','native']:
    summary[condition]={variant:{k:statistics.mean(r[condition+'_'+variant]['components'][k] for r in rows) for k in ['noise_mse','eye_mse_weighted','repa_negative_cosine','repa_weighted','vb','loss']} for variant in ['initialzero','step100']}
# Warm full-model native-condition forward/backward; layer timings include actual NPU kernels.
sample['inpaint_latents']=native;model.train();model.zero_grad(set_to_none=True)
events=[];hooks=[]
for i,block in enumerate(model.transformer_blocks):
    stack=[]
    def pre(module,args,index=i,stack=stack):
        start=torch.npu.Event(enable_timing=True);start.record();stack.append(start)
    def post(module,args,out,index=i,stack=stack):
        end=torch.npu.Event(enable_timing=True);end.record();events.append((index,stack.pop(),end))
    hooks.extend([block.register_forward_pre_hook(pre),block.register_forward_hook(post)])
torch.npu.reset_peak_memory_stats();torch.npu.synchronize();before=time.perf_counter();torch.manual_seed(9999);torch.npu.manual_seed(9999)
loss,terms=training.di_loss(model,training.rows[-1],sample,101);torch.npu.synchronize();forward=time.perf_counter();loss.backward();torch.npu.synchronize();backward=time.perf_counter()
for hook in hooks:hook.remove()
summary['training_native_condition_replay']=dict(loss_terms=terms,forward_seconds=forward-before,backward_seconds=backward-forward,peak_allocated_bytes=torch.npu.max_memory_allocated(),nonzero_gradient_tensors=sum(p.grad is not None and bool(p.grad.any()) for p in params.values()),layer_forward_and_checkpoint_recompute_events=[dict(layer=i,milliseconds=start.elapsed_time(end)) for i,start,end in events],optimizer_update=False)
summary['completed']=True;summary['hardware']=torch.npu.get_device_name(0)
(OUT/'diagnosis.json').write_text(json.dumps(summary,indent=2)+'\n');print('Native-condition full DiTalker loss audit complete',flush=True)
