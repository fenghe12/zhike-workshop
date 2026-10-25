"""Cache genuine 512x512 HDTF base latents and frozen pretrained conditions."""
import argparse,gc,json,os,subprocess,sys,time
from pathlib import Path
import cv2,numpy as np,torch,torch_npu
import torch_npu.contrib.transfer_to_npu
from PIL import Image
H=Path(os.environ['CUSTOM_TRAINING_SESSION']);R=H.parents[1]
OLD=R/'recovery/easyanimate-wans2v-training-3h-20261024'
sys.path[:0]=[str(OLD/'source/EasyAnimate'),str(R/'repos/Wan2.2')]
torch.npu.set_device(0);torch.set_num_threads(8);torch.manual_seed(42)
D='npu:0';rows=json.loads((H/'inputs/training-manifest.json').read_text())
CAPTION='This person is neutral and talks, with natural head movement, consistent identity and a fixed camera.'

def release():gc.collect();torch.npu.empty_cache()
def progress(stage,i=0):print(json.dumps(dict(stage=stage,completed=i,total=50)),flush=True)
def video(row,count):
 r=subprocess.run([str(R/'toolchains/ffmpeg/bin/ffmpeg'),'-v','error','-i',str(H/row['file']),'-vf','crop=min(iw\,ih):min(iw\,ih),scale=512:512','-frames:v',str(count),'-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True)
 f=np.frombuffer(r.stdout,np.uint8).reshape(-1,512,512,3).copy();assert len(f)==count
 return f,torch.from_numpy(f).permute(3,0,1,2).float()/127.5-1

def eye_pose(row,count=16):
 p=np.load(H/'inputs/features'/(row['id']+'.npz'))['eye62'][:count]
 imgs=np.zeros((count,512,512,3),np.uint8)
 for image,points in zip(imgs,p):
  for j,point in enumerate(points):cv2.circle(image,tuple(np.rint(point*511).astype(int)),2,((0,255,0) if j<32 else (255,255,255) if j<52 else (255,0,0)),-1)
 return torch.from_numpy(imgs).permute(3,0,1,2).float()/127.5-1

def ea():
 from easyanimate.models import AutoencoderKLMagvit
 from transformers import T5EncoderModel,T5Tokenizer,CLIPImageProcessor,CLIPVisionModelWithProjection,AutoModel,AutoImageProcessor
 out=H/'inputs/ditalker';out.mkdir(exist_ok=True)
 root=OLD/'models/EasyAnimateV3-XL-2-InP-512x512'
 vae=AutoencoderKLMagvit.from_pretrained(str(root),subfolder='vae',torch_dtype=torch.float32).to(D).eval().requires_grad_(False)
 for i,row in enumerate(rows):
  dest=out/(row['id']+'.pt')
  if dest.exists():continue
  frames,pixels=video(row,64);pixels=pixels[:,::4][None].to(D)
  mask=torch.ones_like(pixels[:,:1]);mask[:,:,:1]=0
  with torch.no_grad(),torch.autocast('npu',dtype=torch.bfloat16):
   latent=vae.encode(pixels).latent_dist.mode()*vae.config.scaling_factor
   inpaint=torch.cat([vae.encode(mask.repeat(1,3,1,1,1)).latent_dist.mode(),vae.encode(pixels*(1-mask)).latent_dist.mode()],dim=1)*vae.config.scaling_factor
  assert latent.shape[2:]==(4,64,64)
  torch.save(dict(latents=latent.cpu().bfloat16(),inpaint_latents=inpaint.cpu().bfloat16()),dest)
  progress('DiTalker VAE',i+1)
 del vae;release()
 tokenizer=T5Tokenizer.from_pretrained(str(root/'tokenizer'))
 text=T5EncoderModel.from_pretrained(str(R/'checkpoints/latte/Latte-1/text_encoder'),torch_dtype=torch.bfloat16).to(D).eval().requires_grad_(False)
 inputs=tokenizer([CAPTION],padding='max_length',max_length=77,truncation=True,return_tensors='pt').to(D)
 with torch.no_grad():embedding=text(**inputs).last_hidden_state.cpu()
 shared=dict(embeddings=embedding,text_mask=inputs.attention_mask.cpu(),clip_mask=torch.ones(1,8),caption=CAPTION)
 del text,inputs;release()
 processor=CLIPImageProcessor.from_pretrained(str(root/'image_encoder'))
 encoder=CLIPVisionModelWithProjection.from_pretrained(str(root/'image_encoder'),torch_dtype=torch.float32).to(D).eval().requires_grad_(False)
 for i,row in enumerate(rows):
  path=out/(row['id']+'.pt');data=torch.load(path,weights_only=False)
  if 'clip_embeds' in data:continue
  frame=video(row,1)[0][0];inputs=processor(images=Image.fromarray(frame),return_tensors='pt').to(D)
  with torch.no_grad(),torch.autocast('npu',dtype=torch.bfloat16):data['clip_embeds']=encoder(**inputs).image_embeds.cpu()
  data.update(shared);torch.save(data,path);progress('DiTalker CLIP',i+1)
 del encoder;release()
 processor=AutoImageProcessor.from_pretrained(str(H/'inputs/dinov2-base'))
 encoder=AutoModel.from_pretrained(str(H/'inputs/dinov2-base'),torch_dtype=torch.bfloat16).to(D).eval().requires_grad_(False)
 for i,row in enumerate(rows):
  path=out/(row['id']+'.pt');data=torch.load(path,weights_only=False)
  if 'dino' in data:continue
  frames,_=video(row,64);indices=[6,22,38,54];features=[]
  for start in range(0,len(indices),4):
   selected=[Image.fromarray(frames[j]) for j in indices[start:start+4]]
   inputs=processor(images=selected,return_tensors='pt').to(D,dtype=torch.bfloat16)
   with torch.no_grad():features.append(encoder(**inputs).last_hidden_state[:,1:].cpu())
  data['dino']=torch.cat(features).bfloat16();assert data['dino'].shape==(4,256,768)
  torch.save(data,path);progress('DiTalker DINOv2',i+1)
 progress('DiTalker data ready',50)

def cog():
 from wan.modules.vae2_1 import Wan2_1_VAE
 from wan.modules.t5 import T5EncoderModel
 from wan.modules.s2v.audio_encoder import AudioEncoder
 out=H/'inputs/cogportrait';out.mkdir(exist_ok=True)
 root=R/'checkpoints/wan2.2-s2v-14b'
 vae=Wan2_1_VAE(vae_pth=str(root/'Wan2.1_VAE.pth'),dtype=torch.bfloat16,device=D)
 for i,row in enumerate(rows):
  dest=out/(row['id']+'.pt')
  if dest.exists():continue
  _,pixels=video(row,16);pixels=pixels.to(D);ref=pixels[:,:1];pose=eye_pose(row,16).to(D)
  with torch.no_grad():
   latent=vae.encode([torch.cat([ref.repeat(1,73,1,1),pixels],dim=1)])[0]
   ref_latent=vae.encode([ref])[0]
   pose_latent=vae.encode([torch.cat([pose[:,:1].repeat(1,73,1,1),pose],dim=1)])[0][:,19:]
  assert latent[:,19:].shape==(16,4,64,64) and pose_latent.shape==(16,4,64,64)
  torch.save(dict(latents=latent[:,19:].cpu(),ref_latents=ref_latent.cpu(),motion_latents=latent[:,:19].cpu(),cond_states=pose_latent.cpu()),dest)
  progress('CogPortrait video and eye pose VAE',i+1)
 del vae;release()
 encoder=T5EncoderModel(text_len=512,dtype=torch.bfloat16,device=torch.device(D),checkpoint_path=str(root/'models_t5_umt5-xxl-enc-bf16.pth'),tokenizer_path=str(root/'google/umt5-xxl'))
 with torch.no_grad():embedding=encoder([CAPTION],torch.device(D))[0].cpu()
 del encoder;release()
 encoder=AudioEncoder(device=D,model_id=str(root/'wav2vec2-large-xlsr-53-english'))
 for i,row in enumerate(rows):
  path=out/(row['id']+'.pt');data=torch.load(path,weights_only=False)
  if 'audio_input' in data:continue
  with torch.no_grad():
   feature=encoder.extract_audio_feat(str(H/'inputs/features'/(row['id']+'.wav')),return_all_layers=True)
   bucket,_=encoder.get_audio_embed_bucket_fps(feature,fps=25,batch_frames=16,m=0)
  data.update(audio_input=bucket[:16].unsqueeze(0).permute(0,2,3,1).cpu(),embeddings=embedding)
  torch.save(data,path);progress('CogPortrait wav2vec',i+1)
 progress('CogPortrait data ready',50)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('model',choices=['ditalker','cogportrait']);a=p.parse_args()
 (ea if a.model=='ditalker' else cog)()
