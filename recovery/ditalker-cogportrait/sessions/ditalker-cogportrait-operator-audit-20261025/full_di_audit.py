"""Full DiTalker: inspect exact trained parameters and isolate preprocessing/decoding."""
import os,sys,io,json,time,gc,collections,subprocess,contextlib
from pathlib import Path
H=Path(os.environ['AUDIT_SESSION']);DATA=H.parent/'ditalker-cogportrait-50hdtf-200steps-20261025';ZERO=H.parent/'ditalker-cogportrait-50hdtf-100steps-allzero-20261025';BASE=H.parent/'easyanimate-wans2v-training-3h-20261024'
os.environ['CUSTOM_TRAINING_SESSION']=str(DATA);sys.path[:0]=[str(DATA),str(BASE/'source/EasyAnimate')]
os.environ['DITALKER_ALLOW_RECORDED_MASK_CACHE']='1'
import train_added_components as training
import torch,numpy as np,requests
from PIL import Image
from easyanimate.models import AutoencoderKLMagvit
from diffusers import DPMSolverMultistepScheduler
torch.backends.mha.set_fastpath_enabled(False)
D='npu:0';ID='WDA_KirstenGillibrand_000_8181_8261';ROW=next(r for r in training.rows if r['id']==ID)
ROOT=BASE/'models/EasyAnimateV3-XL-2-InP-512x512'
OUT=H/'outputs/di';OUT.mkdir(exist_ok=True)
report={}
def save(): (OUT/'diagnosis.json').write_text(json.dumps(report,indent=2)+'\n')
def release():gc.collect();torch.npu.empty_cache()
def stats(x):
    v=x.detach().float();return dict(shape=list(v.shape),dtype=str(x.dtype),finite=bool(torch.isfinite(v).all()),mean=float(v.mean().cpu()),std=float(v.std().cpu()),spatial_std=float(v.std(dim=(-1,-2)).mean().cpu()))
def video_save(video,name):
    a=((video[0].detach().float().cpu().clamp(-1,1)+1)*127.5).round().byte().permute(1,2,3,0).numpy()
    np.save(OUT/(name+'.frames.npy'),a,allow_pickle=False);Image.fromarray(a[len(a)//2]).save(OUT/(name+'.png'))
    return dict(frames=len(a),mean=float(a.mean()),spatial_std=float(a.astype(float).std(axis=(1,2)).mean()))
sample=torch.load(DATA/'inputs/ditalker'/(ID+'.pt'),map_location='cpu',weights_only=False)
raw=subprocess.run([str(H.parents[1]/'toolchains/ffmpeg/bin/ffmpeg'),'-v','error','-i',str(DATA/ROW['file']),'-vf','crop=min(iw\\,ih):min(iw\\,ih),scale=512:512','-frames:v','64','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True).stdout
pixels=torch.from_numpy(np.frombuffer(raw,np.uint8).reshape(64,512,512,3).copy()).permute(3,0,1,2).float()[None,:,::4].to(D)/127.5-1
vae=AutoencoderKLMagvit.from_pretrained(str(ROOT),subfolder='vae',torch_dtype=torch.float32).to(D).eval().requires_grad_(False)
mask=torch.ones_like(pixels[:,:1]);mask[:,:,:1]=0
with torch.no_grad(),torch.autocast('npu',dtype=torch.bfloat16):
    corrected=torch.cat([vae.encode(mask.repeat(1,3,1,1,1)).latent_dist.mode(),vae.encode(pixels*(1-mask)-mask).latent_dist.mode()],dim=1)*vae.config.scaling_factor
    reconstructed=vae.decode(sample['latents'].to(D).float()/vae.config.scaling_factor)[0]
    report['cached_target_VAE_reconstruction']=video_save(reconstructed,'target-reconstruction')
    report['old_vs_correct_masked_video_condition']=dict(old_unknown_pixels=0.,native_unknown_pixels=-1.,mask_latent_identical=bool(torch.equal(corrected[:,:4].cpu().bfloat16(),sample['inpaint_latents'][:,:4])),condition_mae=float((corrected.cpu().float()-sample['inpaint_latents'].float()).abs().mean()),corrected_stats=stats(corrected))
torch.save(dict(inpaint_latents=corrected.cpu().bfloat16(),source=ID,change='unknown masked RGB is -1, following native pipeline'),OUT/'corrected-condition.pt')
old_latent=torch.load(ZERO/'outputs/previews/ditalker-cfg7/generated-latents.pt',map_location='cpu',weights_only=False).to(D)
with torch.no_grad(),torch.autocast('npu',enabled=False):
    decoded=vae.decode(old_latent.float()/vae.config.scaling_factor)[0]
    report['same_old_CFG7_latents_FP32_decode']=video_save(decoded,'old100-cfg7-fp32-raw-decode')
del vae,pixels,mask,reconstructed,decoded,old_latent;release();save()
print('VAE reconstruction and masked-video normalization controls complete',flush=True)
model,details=training.make_ditalker();params={n:p for n,p in model.named_parameters() if p.requires_grad}
plan=json.loads((H/'checkpoint-plans/read.private.json').read_text())['ditalker'];buffer=io.BytesIO()
with requests.get(plan['read_url'],stream=True,timeout=(30,180)) as response:
    if response.status_code!=200:raise RuntimeError('Private weights unavailable')
    for chunk in response.iter_content(8*1024**2):buffer.write(chunk)
assert buffer.tell()==plan['bytes'];buffer.seek(0);payload=torch.load(buffer,map_location='cpu',weights_only=False);buffer.close()
assert payload['step']==100 and set(payload['added_state'])==set(params)
nonzero={}
with torch.no_grad():
    for n,p in params.items():
        v=payload['added_state'][n];p.copy_(v.to(D));count=int(torch.count_nonzero(v))
        if count:nonzero[n]=dict(elements=p.numel(),nonzero_elements=count,max_abs=float(v.abs().max()),l2_norm=float(v.norm()),is_bias=n.endswith('.bias'))
    buffers=dict(model.named_buffers())
    for n,v in payload.get('added_buffers',{}).items():buffers[n].copy_(v.to(D))
report['checkpoint100_nonzero_parameters']=nonzero
report['checkpoint100_nonzero_elements']=sum(v['nonzero_elements'] for v in nonzero.values())
report['all_nonzero_parameter_tensors_are_biases']=all(v['is_bias'] for v in nonzero.values())
saved_nonzero={n:params[n].detach().cpu().clone() for n in nonzero}
del payload;release();save()
# Execute the complete original training loss and backward, recording every tensor.
hook_outputs={}
def hook(name):
    def call(module,args,output):
        if isinstance(output,torch.Tensor):hook_outputs[name]=stats(output)
        elif isinstance(output,tuple) and all(isinstance(v,torch.Tensor) for v in output):hook_outputs[name]=[stats(v) for v in output]
    return call
hooks=[]
for name,module in model.named_modules():
    if name in ['scale_adapter','pose_adapter','repa_proj','audio_projection','style_model','style_content_model','style_content_decoder','style_projection','transformer_blocks.0.audio_attention','transformer_blocks.0.style_attention','transformer_blocks.0.emotion_cross_attention']:
        hooks.append(module.register_forward_hook(hook(name)))
model.train();torch.manual_seed(1234);model.zero_grad(set_to_none=True);torch.npu.synchronize();before=time.perf_counter()
loss,parts=training.di_loss(model,ROW,sample,1);torch.npu.synchronize();forward=time.perf_counter();loss.backward();torch.npu.synchronize();backward=time.perf_counter()
gradients={n:dict(gradient_none=p.grad is None,gradient_norm=float(p.grad.detach().float().norm().cpu()) if p.grad is not None else None,gradient_finite=bool(torch.isfinite(p.grad).all()) if p.grad is not None else None) for n,p in params.items()}
report['full_training_replay']=dict(native_loss=float(loss.detach().cpu()),native_loss_terms=parts,forward_seconds=forward-before,backward_seconds=backward-forward,peak_allocated_bytes=torch.npu.max_memory_allocated(),nonzero_gradient_tensor_count=sum(v['gradient_norm'] is not None and v['gradient_norm']>0 for v in gradients.values()),gradients=gradients,module_outputs=hook_outputs)
for h in hooks:h.remove()
model.zero_grad(set_to_none=True);model.eval().requires_grad_(False);del loss;release();save()
audio=torch.load(DATA/'inputs/features'/(ID+'-audio.pt'),map_location='cpu',weights_only=False)
style=torch.from_numpy(np.load(DATA/'inputs/features'/(ID+'-3dmm.npy')))[None].to(D)
positive=dict(added_cond_kwargs={'resolution':None,'aspect_ratio':None},inpaint_latents=sample['inpaint_latents'].to(D),pad_mask=None,return_dict=False,encoder_hidden_states=sample['embeddings'].to(D),encoder_attention_mask=sample['text_mask'].to(D),clip_encoder_hidden_states=sample['clip_embeds'].to(D),clip_attention_mask=sample['clip_mask'].to(D),audio_encoder_hidden_states=audio['whisper'][None].to(D),phoneme_win=audio['phoneme_win'][None].to(D),style_clip=style,pixel_values_pose=training.pose(ROW))
def generate(name,condition,zero_added=False):
    if zero_added:
        with torch.no_grad():
            for n in nonzero:params[n].zero_()
    scheduler=DPMSolverMultistepScheduler.from_pretrained(str(ROOT),subfolder='scheduler');scheduler.set_timesteps(25,device=D)
    torch.manual_seed(42);latent=torch.randn(sample['latents'].shape,device=D,dtype=torch.float32)*scheduler.init_noise_sigma
    log=[];model.repa_frame_index=0
    with torch.no_grad(),torch.autocast('npu',dtype=torch.bfloat16):
        for i,t in enumerate(scheduler.timesteps):
            kwargs=dict(positive,inpaint_latents=condition)
            if i<len(scheduler.timesteps)*.5:
                kwargs['clip_encoder_hidden_states']=torch.zeros_like(positive['clip_encoder_hidden_states']);kwargs['clip_attention_mask']=torch.zeros_like(positive['clip_attention_mask'])
            out=model(scheduler.scale_model_input(latent,t),timestep=t[None],**kwargs)[0]
            latent=scheduler.step(out.chunk(2,dim=1)[0],t,latent,return_dict=False)[0]
            log.append(dict(step=i+1,timestep=float(t.cpu()),prediction=stats(out),latent=stats(latent)))
    torch.save(latent.cpu(),OUT/(name+'-latents.pt'))
    report[name]=dict(cfg=1,steps=25,seed=42,added_weights='initial_allzero' if zero_added else 'strict100',sampling_trace=log)
    if zero_added:
        with torch.no_grad():
            for n,v in saved_nonzero.items():params[n].copy_(v.to(D))
    save();print('Generated full-model isolation case '+name,flush=True)
generate('strict100-old-mask',sample['inpaint_latents'].to(D))
generate('strict100-native-mask',corrected)
generate('initialzero-native-mask',corrected,True)
del model,params,positive,audio,style;release()
vae=AutoencoderKLMagvit.from_pretrained(str(ROOT),subfolder='vae',torch_dtype=torch.float32).to(D).eval().requires_grad_(False)
for name in ['strict100-old-mask','strict100-native-mask','initialzero-native-mask']:
    latent=torch.load(OUT/(name+'-latents.pt'),map_location='cpu',weights_only=False).to(D)
    with torch.no_grad(),torch.autocast('npu',dtype=torch.bfloat16):
        video=vae.decode(latent/vae.config.scaling_factor)[0].clamp(-1,1);mini=int(vae.mini_batch_encoder)
        if video.shape[2]>mini:
            left=mini//2;right=mini-left
            middle=vae.decode(vae.encode(video[:,:,left:-right])[0].sample())[0]
            video[:,:,left:-right]=(video[:,:,left:-right]+middle)/2
    report[name]['video']=video_save(video,name);save()
report['completed']=True;report['hardware']=torch.npu.get_device_name(0);save();print('Full DiTalker isolation audit complete',flush=True)
