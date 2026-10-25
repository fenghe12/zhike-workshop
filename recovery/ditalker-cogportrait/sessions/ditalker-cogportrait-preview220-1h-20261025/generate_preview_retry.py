"""Generate visible outputs from the actual trained added weights and full frozen bases."""
import gc,io,json,os,sys,time
from pathlib import Path
import requests
H=Path(os.environ['PREVIEW_SESSION']);R=H.parents[1]
TRAIN=H.parent/'ditalker-cogportrait-50hdtf-200steps-20261025'
BASE=H.parent/'easyanimate-wans2v-training-3h-20261024'
os.environ['CUSTOM_TRAINING_SESSION']=str(TRAIN)
sys.path[:0]=[str(TRAIN),str(BASE/'source/EasyAnimate')]
import train_added_components as training
import numpy as np,torch,torch.nn.functional as F
from PIL import Image
# Eval-only native MHA requires matching BF16 qkv and bias on this CANN version.
# Keep the general MHA path already exercised by real training with FP32 added weights.
torch.backends.mha.set_fastpath_enabled(False)
D='npu:0'
ID='WDA_KirstenGillibrand_000_8181_8261'
ROW=next(r for r in training.rows if r['id']==ID)

def release():gc.collect();torch.npu.empty_cache()

def load_added(model,name):
    plan=json.loads((H/'checkpoint-plans'/f'{name}-220.private.json').read_text())
    buffer=io.BytesIO()
    try:
        with requests.get(plan['read_url'],stream=True,timeout=(30,180)) as response:
            if response.status_code!=200:raise RuntimeError('Private trained-weight read failed')
            for chunk in response.iter_content(8*1024**2):buffer.write(chunk)
        assert buffer.tell()==plan['bytes'];buffer.seek(0)
        payload=torch.load(buffer,map_location='cpu',weights_only=False)
    except Exception:raise RuntimeError('Private trained-weight read failed; private URLs omitted') from None
    finally:buffer.close()
    assert payload['step']==220 and payload['model']==name
    parameters={n:p for n,p in model.named_parameters() if p.requires_grad}
    assert set(parameters)==set(payload['added_state'])
    with torch.no_grad():
        for n,p in parameters.items():p.copy_(payload['added_state'][n].to(p.device))
    count=sum(p.numel() for p in parameters.values())
    model.eval().requires_grad_(False)
    del payload;release()
    return dict(checkpoint_step=220,weight_object=plan['object'],loaded_added_parameters=count)

def export(frames,name,info,started):
    if frames.ndim==5:frames=frames[0]
    assert frames.shape[0]==3 and frames.shape[-2:]==(512,512)
    frames=frames.detach().float().cpu();assert bool(torch.isfinite(frames).all())
    array=((frames.clamp(-1,1)+1)*127.5).round().byte().permute(1,2,3,0).numpy()
    out=H/'outputs'/os.environ.get('PREVIEW_VARIANT',name);out.mkdir(parents=True,exist_ok=True)
    np.save(out/'generated.frames.npy',array,allow_pickle=False)
    Image.fromarray(array[len(array)//2]).save(out/'generated.png')
    info.update(model=name,source_sample=ID,source_split='published_train',resolution=[512,512],frames=len(array),fps=6.25 if name=='ditalker' else 25,elapsed_seconds=time.time()-started,hardware=torch.npu.get_device_name(0),peak_allocated_bytes=torch.npu.max_memory_allocated(),pixel_mean=float(array.mean()),pixel_std=float(array.std()),adjacent_frame_mean_abs_difference=float(np.abs(np.diff(array.astype(np.int16),axis=0)).mean()),training_quality_claim=False)
    (out/'result.json').write_text(json.dumps(info,indent=2)+'\n')
    print(json.dumps(dict(stage='generated actual trained-weight preview',**info)),flush=True)

def negative_di():
    from transformers import T5EncoderModel,T5Tokenizer
    root=BASE/'models/EasyAnimateV3-XL-2-InP-512x512'
    cache=H/'inputs/negative-di.pt'
    if cache.exists():
        data=torch.load(cache,map_location='cpu',weights_only=False)
        return data['embedding'],data['mask']
    tokenizer=T5Tokenizer.from_pretrained(str(root/'tokenizer'))
    encoder=T5EncoderModel.from_pretrained(str(R/'checkpoints/latte/Latte-1/text_encoder'),torch_dtype=torch.bfloat16).to(D).eval().requires_grad_(False)
    inputs=tokenizer([''],padding='max_length',max_length=77,truncation=True,return_tensors='pt').to(D)
    with torch.no_grad():embedding=encoder(**inputs).last_hidden_state.cpu();mask=inputs.attention_mask.cpu()
    torch.save(dict(embedding=embedding,mask=mask),cache)
    del encoder,inputs;release()
    return embedding,mask

def ditalker():
    from diffusers import DPMSolverMultistepScheduler
    from easyanimate.models import AutoencoderKLMagvit
    started=time.time();out=H/'outputs'/os.environ.get('PREVIEW_VARIANT','ditalker');out.mkdir(parents=True,exist_ok=True)
    cfg=float(os.environ.get('DITALKER_CFG','7'))
    print('Encoding empty-text CFG condition',flush=True)
    negative,negative_mask=negative_di()
    model,details=training.make_ditalker();info=load_added(model,'ditalker')
    sample=torch.load(TRAIN/'inputs/ditalker'/(ID+'.pt'),map_location='cpu',weights_only=False)
    audio=torch.load(TRAIN/'inputs/features'/(ID+'-audio.pt'),map_location='cpu',weights_only=False)
    style=torch.from_numpy(np.load(TRAIN/'inputs/features'/(ID+'-3dmm.npy')))[None].to(D)
    common=dict(added_cond_kwargs={'resolution':None,'aspect_ratio':None},inpaint_latents=sample['inpaint_latents'].to(D),pad_mask=None,return_dict=False)
    positive=dict(common,encoder_hidden_states=sample['embeddings'].to(D),encoder_attention_mask=sample['text_mask'].to(D),clip_encoder_hidden_states=sample['clip_embeds'].to(D),clip_attention_mask=sample['clip_mask'].to(D),audio_encoder_hidden_states=audio['whisper'][None].to(D),phoneme_win=audio['phoneme_win'][None].to(D),style_clip=style,pixel_values_pose=training.pose(ROW))
    negative_kwargs=dict(common,encoder_hidden_states=negative.to(D),encoder_attention_mask=negative_mask.to(D))
    for key in ['clip_encoder_hidden_states','clip_attention_mask','audio_encoder_hidden_states','phoneme_win','style_clip','pixel_values_pose']:negative_kwargs[key]=torch.zeros_like(positive[key])
    root=BASE/'models/EasyAnimateV3-XL-2-InP-512x512'
    scheduler=DPMSolverMultistepScheduler.from_pretrained(str(root),subfolder='scheduler')
    scheduler.set_timesteps(25,device=D)
    torch.manual_seed(42);torch.npu.reset_peak_memory_stats()
    latent=torch.randn(sample['latents'].shape,device=D,dtype=torch.float32)*scheduler.init_noise_sigma
    model.repa_frame_index=0;durations=[]
    with torch.no_grad(),torch.autocast('npu',dtype=torch.bfloat16):
        for i,t in enumerate(scheduler.timesteps):
            torch.npu.synchronize();before=time.perf_counter()
            x=scheduler.scale_model_input(latent,t)
            conditional=dict(positive)
            if i<len(scheduler.timesteps)*.5:
                conditional['clip_encoder_hidden_states']=torch.zeros_like(positive['clip_encoder_hidden_states'])
                conditional['clip_attention_mask']=torch.zeros_like(positive['clip_attention_mask'])
            c=model(x,timestep=t[None],**conditional)[0]
            if cfg>1:
                u=model(x,timestep=t[None],**negative_kwargs)[0]
                predicted=(u+cfg*(c-u)).chunk(2,dim=1)[0]
            else:predicted=c.chunk(2,dim=1)[0]
            latent=scheduler.step(predicted,t,latent,return_dict=False)[0]
            assert bool(torch.isfinite(latent).all());torch.npu.synchronize();durations.append(time.perf_counter()-before)
            print(json.dumps(dict(model='ditalker',sampling_step=i+1,total=25,step_seconds=durations[-1])),flush=True)
    torch.save(latent.detach().cpu(),out/'generated-latents.pt')
    model.cpu();del model,positive,negative_kwargs,common;release()
    print('Decoding DiTalker generated latents',flush=True)
    vae=AutoencoderKLMagvit.from_pretrained(str(root),subfolder='vae',torch_dtype=torch.float32).to(D).eval().requires_grad_(False)
    decode_rng=torch.npu.get_rng_state()
    with torch.no_grad(),torch.autocast('npu',dtype=torch.bfloat16):
        video=vae.decode(latent/vae.config.scaling_factor)[0].clamp(-1,1)
        # Preserve the source pipeline's middle-frame VAE smoothing.
        mini=int(vae.mini_batch_encoder)
        if video.shape[2]>mini:
            left=mini//2;right=mini-left
            middle=vae.decode(vae.encode(video[:,:,left:-right])[0].sample())[0]
            video[:,:,left:-right]=(video[:,:,left:-right]+middle)/2
    info.update(sampling_steps=25,cfg=cfg,seed=42,scheduler='DPMSolverMultistepScheduler from released EasyAnimate scheduler config',source_frame_stride=4,sampling_seconds=sum(durations),sampling_step_seconds=durations,conditioning='Original cached reference, Whisper, phoneme, 3DMM style, text, and pose; empty-text and zero auxiliary CFG branch',scope='All eleven trained added groups retained',latent_mean=float(latent.float().mean().cpu()),latent_std=float(latent.float().std().cpu()),vae_decode_precision='BF16 autocast')
    export(video,'ditalker',info,started)
    if os.environ.get('CHECK_FP32_VAE')=='1':
        del video;release()
        print('Checking the same generated latents with FP32 VAE decoding',flush=True)
        torch.npu.set_rng_state(decode_rng)
        with torch.no_grad(),torch.autocast('npu',enabled=False):
            video=vae.decode(latent.float()/vae.config.scaling_factor)[0].clamp(-1,1)
            if video.shape[2]>mini:
                middle=vae.decode(vae.encode(video[:,:,left:-right])[0].sample())[0]
                video[:,:,left:-right]=(video[:,:,left:-right]+middle)/2
        previous=os.environ.get('PREVIEW_VARIANT','ditalker')
        os.environ['PREVIEW_VARIANT']=previous+'-fp32vae'
        export(video,'ditalker',dict(info,vae_decode_precision='FP32, autocast disabled'),started)

def cogportrait():
    from wan.modules.vae2_1 import Wan2_1_VAE
    from wan.modules.t5 import T5EncoderModel
    from wan.modules.s2v.audio_encoder import AudioEncoder
    from wan.utils.fm_solvers_unipc import FlowUniPCMultistepScheduler
    import prepare_npu_data
    started=time.time();root=R/'checkpoints/wan2.2-s2v-14b'
    sample=torch.load(TRAIN/'inputs/cogportrait'/(ID+'.pt'),map_location='cpu',weights_only=False)
    print('Preparing real 64-frame pose and audio conditions',flush=True)
    pose=prepare_npu_data.eye_pose(ROW,64).to(D)
    vae=Wan2_1_VAE(vae_pth=str(root/'Wan2.1_VAE.pth'),dtype=torch.bfloat16,device=D)
    with torch.no_grad():cond=vae.encode([torch.cat([pose[:,:1].repeat(1,73,1,1),pose],dim=1)])[0][:,19:].cpu()
    assert cond.shape==(16,16,64,64)
    del pose,vae;release()
    encoder=AudioEncoder(device=D,model_id=str(root/'wav2vec2-large-xlsr-53-english'))
    with torch.no_grad():
        feature=encoder.extract_audio_feat(str(TRAIN/'inputs/features'/(ID+'.wav')),return_all_layers=True)
        bucket,_=encoder.get_audio_embed_bucket_fps(feature,fps=25,batch_frames=64,m=0)
        audio=bucket[:64].unsqueeze(0).permute(0,2,3,1).cpu()
    del encoder,feature,bucket;release()
    encoder=T5EncoderModel(text_len=512,dtype=torch.bfloat16,device=torch.device(D),checkpoint_path=str(root/'models_t5_umt5-xxl-enc-bf16.pth'),tokenizer_path=str(root/'google/umt5-xxl'))
    with torch.no_grad():negative=encoder([''],torch.device(D))[0].cpu()
    del encoder;release()
    model,details=training.make_cog();info=load_added(model,'cogportrait')
    positive=dict(context=[sample['embeddings'].to(D,dtype=torch.bfloat16)],seq_len=16*64*64//4,ref_latents=[sample['ref_latents'].to(D,dtype=torch.bfloat16)],motion_latents=[sample['motion_latents'].to(D,dtype=torch.bfloat16)],cond_states=[cond.to(D,dtype=torch.bfloat16)],audio_input=audio.to(D,dtype=torch.bfloat16),motion_frames=[73,19],drop_motion_frames=False)
    negative_kwargs=dict(positive,context=[negative.to(D,dtype=torch.bfloat16)],audio_input=torch.zeros_like(positive['audio_input']))
    scheduler=FlowUniPCMultistepScheduler(num_train_timesteps=1000,shift=1,use_dynamic_shifting=False)
    scheduler.set_timesteps(40,device=D,shift=3.)
    torch.manual_seed(42);generator=torch.Generator(device=D).manual_seed(42)
    latent=torch.randn((16,16,64,64),device=D,dtype=torch.bfloat16,generator=generator)
    torch.npu.reset_peak_memory_stats();durations=[]
    with torch.no_grad(),torch.autocast('npu',dtype=torch.bfloat16):
        for i,t in enumerate(scheduler.timesteps):
            torch.npu.synchronize();before=time.perf_counter()
            c=model([latent],t=t[None],**positive)[0]
            u=model([latent],t=t[None],**negative_kwargs)[0]
            prediction=u+4.5*(c-u)
            latent=scheduler.step(prediction[None],t,latent[None],return_dict=False,generator=generator)[0][0]
            assert bool(torch.isfinite(latent).all());torch.npu.synchronize();durations.append(time.perf_counter()-before)
            print(json.dumps(dict(model='cogportrait',sampling_step=i+1,total=40,step_seconds=durations[-1])),flush=True)
    model.cpu();del model,positive,negative_kwargs;release()
    print('Decoding CogPortrait generated latents with native motion history',flush=True)
    vae=Wan2_1_VAE(vae_pth=str(root/'Wan2.1_VAE.pth'),dtype=torch.bfloat16,device=D)
    with torch.no_grad():video=vae.decode([torch.cat([sample['motion_latents'].to(D,dtype=torch.bfloat16),latent.to(torch.bfloat16)],dim=1)])[0][:,-64:]
    info.update(sampling_steps=40,cfg=4.5,shift=3.,seed=42,scheduler='native FlowUniPCMultistepScheduler',sampling_seconds=sum(durations),sampling_step_seconds=durations,conditioning='Real 64-frame audio and measured 62-point eye/upper-face pose; reference-only repeated frame history',scope='Trained pose branch only; agent planner and KTO are absent')
    export(video,'cogportrait',info,started)

if __name__=='__main__':
    (ditalker if sys.argv[1]=='ditalker' else cogportrait)()
