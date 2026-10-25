"""Full-backbone real-data training of newly added DiTalker / CogPortrait components."""
import argparse,collections,gc,json,math,os,sys,time,subprocess
from pathlib import Path
import cv2,numpy as np,torch,torch.nn.functional as F,torch_npu
import torch_npu.contrib.transfer_to_npu
from torch.utils.checkpoint import checkpoint
from safetensors.torch import load_file
H=Path(os.environ['CUSTOM_TRAINING_SESSION']);R=H.parents[1]
OLD=R/'recovery/easyanimate-wans2v-training-3h-20261024'
sys.path[:0]=[str(H/'source/DiTalker-CVIU'),str(R/'repos/Wan2.2')]
D='npu:0';torch.npu.set_device(0);torch.set_num_threads(8);torch.manual_seed(42)
rows=json.loads((H/'inputs/training-manifest.json').read_text());assert len(rows)==50
# Fused NPU attention, with padding preserving the original dot-product scale.
original_sdpa=F.scaled_dot_product_attention
attention_calls=0

def npu_sdpa(q,k,v,attn_mask=None,dropout_p=0.,is_causal=False,scale=None,enable_gqa=False):
 global attention_calls
 if q.device.type!='npu':return original_sdpa(q,k,v,attn_mask=attn_mask,dropout_p=dropout_p,is_causal=is_causal,scale=scale,enable_gqa=enable_gqa)
 dim=q.shape[-1];vdim=v.shape[-1];target=math.ceil(max(dim,vdim)/16)*16
 if enable_gqa:
  k=k.repeat_interleave(q.shape[1]//k.shape[1],dim=1);v=v.repeat_interleave(q.shape[1]//v.shape[1],dim=1)
 mask=attn_mask
 if mask is not None:
  if mask.dtype==torch.bool:mask=~mask
  else:
   assert not bool((mask>0).any()),'Additive positive attention bias needs a separate supported implementation'
   mask=mask<0
  mask=mask.to(D)
  if mask.ndim==2:mask=mask[None,None]
  elif mask.ndim==3:mask=mask[:,None]
  if mask.shape[-2]==1 and q.shape[-2]!=1:
   mask=mask.expand(*mask.shape[:-2],q.shape[-2],mask.shape[-1])
  mask=mask.contiguous()
 if is_causal:
  causal=torch.ones(q.shape[-2],k.shape[-2],device=q.device,dtype=torch.bool).triu(1)
  mask=causal if mask is None else mask|causal
 q=F.pad(q,(0,target-dim)).bfloat16().contiguous();k=F.pad(k,(0,target-dim)).bfloat16().contiguous();v=F.pad(v,(0,target-vdim)).bfloat16().contiguous()
 output=torch_npu.npu_fusion_attention(q,k,v,head_num=q.shape[1],input_layout='BNSD',atten_mask=mask,scale=scale if scale is not None else dim**-.5,keep_prob=1-dropout_p)[0]
 attention_calls+=1
 return output[...,:vdim]
F.scaled_dot_product_attention=npu_sdpa

def group(name):
 for item in ['audio_projection','style_content_decoder','style_content_model','style_projection','style_model','scale_adapter','pose_adapter','repa_proj','emotion_cross_attention','audio_attention','style_attention']:
  if item in name:return item
 return name.split('.')[0]

def make_ditalker():
 from ditalker.models.base.transformer3d import Transformer3DModel
 root=OLD/'models/EasyAnimateV3-XL-2-InP-512x512/transformer'
 config=json.loads((root/'config.json').read_text())
 config.update(enable_audio_attention=True,enable_style_attn=True,enable_scale_fusion=True,enable_audio_scale_fusion=True,enable_eca=True,enable_pose_adapter=True,enable_repa_2=True,enable_repa_1=False)
 model=Transformer3DModel.from_config(config)
 state=load_file(str(root/'diffusion_pytorch_model.safetensors'))
 result=model.load_state_dict(state,strict=False)
 assert not result.unexpected_keys,result.unexpected_keys
 known=set(state);missing=[n for n,p in model.named_parameters() if n not in known]
 for n in missing:
  assert any(item in n for item in ['audio_projection','style_','scale_adapter','pose_adapter','repa_proj','audio_attention','emotion_cross_attention']),n
 model.requires_grad_(False)
 for name,param in model.named_parameters():
  if name in missing:param.requires_grad_(True)
  else:param.data=param.data.to(torch.bfloat16)
 zeros=[]
 for i,block in enumerate(model.transformer_blocks):
  for name in ['audio_attention','style_attention','emotion_cross_attention']:
   module=getattr(block,name,None)
   assert module is not None,(i,name)
   torch.nn.init.zeros_(module.to_out[0].weight)
   if module.to_out[0].bias is not None:torch.nn.init.zeros_(module.to_out[0].bias)
   zeros.append('transformer_blocks.'+str(i)+'.'+name+'.to_out.0')
 # PoseGuider already defines a zero output convolution. Keep scale heads at tanh(1)
 # to avoid multiplying two independently zero-initialized branches.
 assert not bool(model.pose_adapter.conv_out.weight.detach().any())
 model.gradient_checkpointing=True
 model=model.to(D)
 return model,dict(base_weights=str(root),new_parameter_names=missing,zero_output_layers=zeros+['pose_adapter.conv_out'],repa='Full 8th-block frame grid pooled to 16x16 and aligned to its real DINOv2 frame')

def make_cog():
 from wan.modules.s2v.model_s2v import WanModel_S2V
 from wan_training_adapter import install_adapters
 root=R/'checkpoints/wan2.2-s2v-14b'
 model,info=WanModel_S2V.from_pretrained(str(root),torch_dtype=torch.bfloat16,low_cpu_mem_usage=True,output_loading_info=True)
 assert not info['missing_keys'] and not info['unexpected_keys']
 model.requires_grad_(False)
 # This is exactly the native 3D-convolution pose-injection location before patch tokens.
 old=model.cond_encoder
 class AddedPoseCondition(torch.nn.Module):
  def __init__(self,original):
   super().__init__();self.original=original
   self.added=torch.nn.Conv3d(original.in_channels,original.out_channels,kernel_size=original.kernel_size,stride=original.stride,padding=original.padding,bias=original.bias is not None)
   torch.nn.init.zeros_(self.added.weight)
   if self.added.bias is not None:torch.nn.init.zeros_(self.added.bias)
  def forward(self,pose_latents):
   # Preserve the original zero-pose baseline and train only the extra pose branch.
   return self.original(torch.zeros_like(pose_latents))+self.added(pose_latents)
 model.cond_encoder=AddedPoseCondition(old)
 model.time_embedding.float();model.time_projection.float();model.head.float()
 install_adapters()
 for block in model.blocks:
  original=block.forward
  def forward(*args,_forward=original,**kwargs):
   return checkpoint(_forward,*args,use_reentrant=False,**kwargs) if torch.is_grad_enabled() else _forward(*args,**kwargs)
  block.forward=forward
 return model.to(D),dict(base_weights=str(root),zero_output_layers=['cond_encoder.added'],new_parameter_names=['cond_encoder.added.weight','cond_encoder.added.bias'],pose_path='Measured HDTF upper-face/eye 62 keypoints -> pose RGB -> native Wan VAE -> zero-initialized Conv3d -> full Wan S2V backbone',scope='Pose-conditioned FM training; agent planner and KTO preference fine-tuning are not claimed')

def pose(row):
 points=np.load(H/'inputs/features'/(row['id']+'.npz'))['landmarks'][:64]
 contour=[10,338,297,332,284,251,389,356,454,323,361,288,397,365,379,378,400,377,152,148,176,149,150,136,172,58,132,93,234,127,162,21,54,103,67,109]
 points=points[::4]
 images=np.zeros((16,256,256,3),np.uint8)
 for image,p in zip(images,points):
  q=np.rint(p[contour,:2]*255).astype(np.int32)
  cv2.polylines(image,[q],True,(255,255,255),1,cv2.LINE_AA)
  # Orientation is represented by the nose position; no inner eye/mouth contours.
  cv2.circle(image,tuple(np.rint(p[1,:2]*255).astype(int)),2,(255,0,0),-1)
 return torch.from_numpy(images).permute(3,0,1,2)[None].to(D).float()/127.5-1

def validated_di_sample(sample,identifier):
 # Old experiment caches remain available only for an explicitly requested comparison.
 directory=os.environ.get('DITALKER_CONDITIONS_DIR')
 if directory:
  replacement=torch.load(Path(directory)/(identifier+'.pt'),map_location='cpu',weights_only=False)
  assert replacement.get('preprocessing_version')=='native_mask_unknown_minus_one_v1'
  assert replacement['inpaint_latents'].shape==sample['inpaint_latents'].shape
  sample=dict(sample,inpaint_latents=replacement['inpaint_latents'],preprocessing_version=replacement['preprocessing_version'])
 if sample.get('preprocessing_version')!='native_mask_unknown_minus_one_v1' and os.environ.get('DITALKER_ALLOW_RECORDED_MASK_CACHE')!='1':
  raise RuntimeError('DiTalker masked-video cache predates the native -1 unknown-pixel fix. Set DITALKER_CONDITIONS_DIR to separately repaired conditions, or regenerate in a fresh persistent session. Historical comparisons must explicitly set DITALKER_ALLOW_RECORDED_MASK_CACHE=1.')
 return sample

def di_loss(model,row,sample,step):
 sample=validated_di_sample(sample,row['id'])
 from ditalker.utils import gaussian_diffusion as gd
 from ditalker.utils.respace import SpacedDiffusion,space_timesteps
 latent=sample['latents'].to(D).float();model.repa_frame_index=(step-1)%latent.shape[2]
 audio=torch.load(H/'inputs/features'/(row['id']+'-audio.pt'),weights_only=False)
 style=torch.from_numpy(np.load(H/'inputs/features'/(row['id']+'-3dmm.npy')))[None].to(D)
 kwargs=dict(encoder_hidden_states=sample['embeddings'].to(D),encoder_attention_mask=sample['text_mask'].to(D),added_cond_kwargs={'resolution':None,'aspect_ratio':None},inpaint_latents=sample['inpaint_latents'].to(D),clip_encoder_hidden_states=sample['clip_embeds'].to(D),clip_attention_mask=sample['clip_mask'].to(D),audio_encoder_hidden_states=audio['whisper'][None].to(D),phoneme_win=audio['phoneme_win'][None].to(D),style_clip=style,pad_mask=None,pixel_values_pose=pose(row),return_dict=False)
 diffusion=SpacedDiffusion(use_timesteps=space_timesteps(1000,'1000'),betas=gd.get_named_beta_schedule('linear',1000),model_mean_type=gd.ModelMeanType.EPSILON,model_var_type=gd.ModelVarType.LEARNED_RANGE,loss_type=gd.LossType.MSE,snr=False,return_startx=False)
 # The native loop expects a list of encoders for the auxiliary feature loss.
 def wrapped(*args,**kw):
  output,repa=model(*args,**kw)
  return output,[repa]
 t=torch.randint(50,950,(1,),device=D)
 target=sample['dino'][model.repa_frame_index:model.repa_frame_index+1].to(D).float()
 eye_points=np.load(H/'inputs/features'/(row['id']+'.npz'))['eye62'][[0,16,32,48]]
 eye_masks=np.zeros((4,64,64),np.float32)
 for mask,points in zip(eye_masks,eye_points):
  for points_eye in [points[:16],points[16:32]]:
   polygon=cv2.convexHull(np.rint(points_eye*63).astype(np.int32));cv2.fillConvexPoly(mask,polygon,1.)
  mask[:]=cv2.dilate(mask,np.ones((3,3),np.uint8))
 region_mask={'eye_region_mask':torch.from_numpy(eye_masks)[None,:,None].to(D)}
 with torch.autocast('npu',dtype=torch.bfloat16):
  result=diffusion.training_losses(wrapped,latent,t,model_kwargs=kwargs,noise=torch.randn_like(latent),enable_repa=True,z=[target],repa_weight=.1,enable_region_mask_loss=True,region_loss_weight=10.,region_mask=region_mask)
 return result['loss'].mean(),{key:float(value.detach().float().mean().cpu()) for key,value in result.items()}

def cog_loss(model,row,sample,step):
 from wan_training_adapter import prediction
 latent=sample['latents'].to(D).float();noise=torch.randn_like(latent)
 sigma=float(torch.rand((),device='cpu')*.9+.05)
 output=prediction(model,sample,noise,sigma=sigma)
 loss=F.mse_loss(output.float(),noise-latent)
 return loss,dict(flow_matching=float(loss.detach().cpu()),sigma=sigma)

def main(a):
 out=H/'outputs'/a.model;out.mkdir(parents=True,exist_ok=True)
 started=time.time();state=dict(model=a.model,target_steps=200,completed_steps=0,data_count=50,resolution=[512,512],frames=16,ditalker_source_frame_stride=4 if a.model=='ditalker' else 1,hardware=torch.npu.get_device_name(0),scope='Frozen pretrained full backbone; all newly added trainable components optimized',training_quality_claim=False)
 def status(stage,**extra):
  state.update(stage=stage,elapsed_seconds=time.time()-started,**extra)
  (out/'status.json').write_text(json.dumps(state,indent=2)+'\n');print(json.dumps(dict(stage=stage,elapsed_seconds=round(time.time()-started),**extra)),flush=True)
 status('loading full modified model')
 model,details=(make_ditalker if a.model=='ditalker' else make_cog)()
 parameters={n:p for n,p in model.named_parameters() if p.requires_grad}
 groups=collections.defaultdict(list)
 for n,p in parameters.items():groups[group(n)].append((n,p))
 state.update(parameter_count=sum(p.numel() for p in model.parameters()),trainable_parameter_count=sum(p.numel() for p in parameters.values()),loading=details,parameter_groups={g:sum(p.numel() for n,p in ps) for g,ps in groups.items()},optimizer='AdamW',learning_rate=2e-5)
 (out/'parameter-manifest.json').write_text(json.dumps(dict(trainable=list(parameters),groups=state['parameter_groups'],loading=details),indent=2)+'\n')
 optimizer=torch.optim.AdamW(parameters.values(),lr=2e-5,betas=(.9,.999),weight_decay=.01,foreach=False)
 snapshots={n:p.detach().flatten()[:64].cpu().clone() for n,p in parameters.items()}
 frozen={n:p for n,p in model.named_parameters() if not p.requires_grad and p.ndim>1}
 frozen_names=list(frozen)[::max(1,len(frozen)//12)][:12]
 frozen_before={n:frozen[n].detach().flatten()[:64].cpu().clone() for n in frozen_names}
 seen=collections.Counter();nonzero_seen=set();model.train();step_records=[]
 loss_fn=di_loss if a.model=='ditalker' else cog_loss
 generator=torch.Generator().manual_seed(42)
 for epoch in range(4):
  order=torch.randperm(50,generator=generator).tolist()
  for index in order:
   step=len(step_records)+1;row=rows[index]
   sample=torch.load(H/'inputs'/a.model/(row['id']+'.pt'),weights_only=False)
   optimizer.zero_grad(set_to_none=True);torch.npu.reset_peak_memory_stats();torch.npu.synchronize();t0=time.perf_counter()
   status('forward and native loss',step=step,sample=row['id'])
   loss,parts=loss_fn(model,row,sample,step);torch.npu.synchronize();t1=time.perf_counter()
   assert bool(torch.isfinite(loss)),('nonfinite loss',step)
   loss.backward();torch.npu.synchronize();t2=time.perf_counter()
   missing=[n for n,p in parameters.items() if p.grad is None]
   norms={g:torch.stack([p.grad.detach().float().norm() for n,p in ps if p.grad is not None]).norm() for g,ps in groups.items()}
   norm=torch.nn.utils.clip_grad_norm_(list(parameters.values()),1.,foreach=False)
   assert bool(torch.isfinite(norm)) and float(norm)>0,('gradient',step)
   active={g:float(value.detach().cpu()) for g,value in norms.items()};nonzero_seen.update(g for g,v in active.items() if v>0)
   optimizer.step();torch.npu.synchronize();t3=time.perf_counter()
   seen[row['id']]+=1
   rec=dict(step=step,sample=row['id'],loss=float(loss.detach().cpu()),loss_terms=parts,forward_loss_seconds=t1-t0,backward_seconds=t2-t1,gradient_inspection_and_update_seconds=t3-t2,gradient_norm=float(norm.detach().cpu()),group_gradient_norms=active,missing_gradient_tensors=missing,peak_allocated_bytes=torch.npu.max_memory_allocated(),peak_reserved_bytes=torch.npu.max_memory_reserved(),fused_attention_calls=attention_calls)
   step_records.append(rec)
   with (out/'steps.jsonl').open('a') as f:f.write(json.dumps(rec)+'\n')
   status('optimizer step complete',completed_steps=step,loss=rec['loss'],step_seconds=t3-t0,peak_GiB=rec['peak_allocated_bytes']/1024**3)
   del loss,sample
   if step in [50,100,150,200]:
    from multipart_checkpoint import CheckpointWriter
    plan=H/'checkpoint-plans'/f'{a.model}-{step}.private.json'
    if plan.exists():
     status('saving private resumable checkpoint',completed_steps=step)
     writer=CheckpointWriter(plan,out/'checkpoint-backup.json')
     payload=dict(model=a.model,step=step,added_state={n:p.detach().cpu() for n,p in parameters.items()},optimizer=optimizer.state_dict(),torch_rng=torch.get_rng_state(),npu_rng=torch.npu.get_rng_state(),sampler_generator_state=generator.get_state(),base=details['base_weights'],config=dict(state),sample_counts=dict(seen))
     torch.save(payload,writer);writer.finish();del payload
 changed={g:[n for n,p in ps if not torch.equal(snapshots[n],p.detach().flatten()[:64].cpu())] for g,ps in groups.items()}
 unchanged_frozen=all(torch.equal(frozen_before[n],frozen[n].detach().flatten()[:64].cpu()) for n in frozen_names)
 assert len(step_records)==200 and len(seen)==50 and set(seen.values())=={4}
 assert nonzero_seen==set(groups),(nonzero_seen,set(groups))
 assert all(changed.values()) and unchanged_frozen
 state.update(completed_steps=200,all_50_samples_seen_4_times=True,all_added_groups_received_nonzero_gradients=True,changed_parameter_tensors_by_group={g:len(v) for g,v in changed.items()},frozen_sampled_parameters_unchanged=unchanged_frozen,steps=step_records,sample_counts=dict(seen))
 status('completed 200 real optimizer steps')
 # A small weights-only export is separate from the resumable private OBS checkpoint.
 writer=CheckpointWriter(H/'checkpoint-plans'/f'{a.model}-weights200.private.json',out/'weights-backup.json')
 torch.save(dict(model=a.model,step=200,base=details['base_weights'],added_state={n:p.detach().cpu() for n,p in parameters.items()},config=state),writer)
 writer.finish()
 subprocess.run([sys.executable,str(H/'inspect_checkpoint.py'),a.model],check=True,env=dict(os.environ,TORCH_DEVICE_BACKEND_AUTOLOAD='0',NPU_MIGRATE='0',PYTHONPATH=''))
 state['checkpoint_inspection']=json.loads((out/'checkpoint-inspection.json').read_text())
 (out/'result.json').write_text(json.dumps(state,indent=2)+'\n')

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('model',choices=['ditalker','cogportrait']);main(p.parse_args())
