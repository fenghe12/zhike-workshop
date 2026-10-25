"""Extract real Whisper, time-aligned phoneme and Deep3DFaceRecon conditions on CPU."""
import gc,json,os,re,subprocess,sys,time,types
from pathlib import Path
import numpy as np,torch
from PIL import Image
from scipy.io import loadmat
from transformers import WhisperForConditionalGeneration,WhisperProcessor,pipeline
H=Path(os.environ['CUSTOM_TRAINING_SESSION']);R=H.parents[1]
torch.set_num_threads(4)
manifest=json.loads((H/'inputs/training-manifest.json').read_text())
# Use the installed original face reconstruction implementation without importing unrelated renderers.
netpath=R/'repos/SadTalker/src/face3d/models/networks.py'
text=netpath.read_text().replace('from .arcface_torch.backbones import get_model','').replace('from kornia.geometry import warp_affine','')
ns={'__name__':'training_face_reconstruction'};exec(compile(text,str(netpath),'exec'),ns)
recon=ns['define_net_recon']('resnet50',use_last_fc=False,init_path=None).eval().requires_grad_(False)
weights=torch.load(R/'checkpoints/sadtalker/epoch_20.pth',map_location='cpu',weights_only=False)
recon.load_state_dict(weights['net_recon'],strict=True);del weights
prepath=R/'repos/SadTalker/src/face3d/util/preprocess.py'
text=prepath.read_text().replace('warnings.filterwarnings("ignore", category=np.VisibleDeprecationWarning)','')
ns={'__name__':'training_face_preprocessing'};exec(compile(text,str(prepath),'exec'),ns)
align=ns['align_img']
lm3d=loadmat(R/'checkpoints/sadtalker/BFM_Fitting/similarity_Lm3D_all.mat')['lm']
lm_idx=np.array([31,37,40,43,46,49,55])-1
lm3d=np.stack([lm3d[lm_idx[0]],lm3d[lm_idx[[1,2]]].mean(0),lm3d[lm_idx[[3,4]]].mean(0),lm3d[lm_idx[5]],lm3d[lm_idx[6]]])[[1,2,0,3,4]]
for i,row in enumerate(manifest):
    dest=H/'inputs/features'/(row['id']+'-3dmm.npy')
    if dest.exists():continue
    feature=np.load(H/'inputs/features'/(row['id']+'.npz'))
    result=subprocess.run([str(R/'toolchains/ffmpeg/bin/ffmpeg'),'-v','error','-i',str(H/row['file']),'-vf','crop=min(iw\,ih):min(iw\,ih),scale=512:512','-frames:v','64','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True)
    frames=np.frombuffer(result.stdout,np.uint8).reshape(-1,512,512,3)
    aligned=[]
    for img,landmarks in zip(frames,feature['five_points']):
        lm=landmarks.copy();lm[:,1]=511-lm[:,1]
        _,image,_,_=align(Image.fromarray(img),lm,lm3d)
        aligned.append(torch.from_numpy(np.array(image,dtype=np.float32)/255).permute(2,0,1))
    coeff=[]
    with torch.no_grad():
        for begin in range(0,64,8):coeff.append(recon(torch.stack(aligned[begin:begin+8]))[:,80:144].numpy())
    coeff=np.concatenate(coeff);assert coeff.shape==(64,64) and np.isfinite(coeff).all()
    np.save(dest,coeff)
    print(json.dumps(dict(stage='Deep3DFaceRecon',completed=i+1,total=50)),flush=True)
del recon;gc.collect()
# CMU ARPAbet mapping. Word intervals come from Whisper token alignment.
phones='AA AE AH AO AW AY B CH D DH EH ER EY F G HH IH IY JH K L M N NG OW OY P R S SH T TH UH UW V W Y Z ZH'.split()
idmap={p:i+1 for i,p in enumerate(phones)};idmap.update(SIL=0,UNK=40)
lexicon={}
for line in (H/'inputs/cmudict.dict').read_text().splitlines():
    if not line or line.startswith(';;;'):continue
    parts=line.split();word=re.sub(r'\(\d+\)$','',parts[0]).lower()
    lexicon.setdefault(word,[re.sub('[012]','',p) for p in parts[1:]])
checkpoint=R/'checkpoints/whisper-tiny'
processor=WhisperProcessor.from_pretrained(str(checkpoint),local_files_only=True)
model=WhisperForConditionalGeneration.from_pretrained(str(checkpoint),local_files_only=True,attn_implementation='eager').eval().requires_grad_(False)
recognizer=pipeline('automatic-speech-recognition',model=model,tokenizer=processor.tokenizer,feature_extractor=processor.feature_extractor,device=-1)
records=[]
for i,row in enumerate(manifest):
    target=H/'inputs/features'/(row['id']+'-audio.pt')
    if target.exists():continue
    audio=H/'inputs/features'/(row['id']+'.wav')
    subprocess.run([str(R/'toolchains/ffmpeg/bin/ffmpeg'),'-v','error','-y','-i',str(H/row['file']),'-t',str(64/25),'-vn','-ar','16000','-ac','1',str(audio)],check=True)
    import soundfile as sf
    samples,sr=sf.read(audio);assert sr==16000 and len(samples)>4000
    inputs=processor.feature_extractor(samples,sampling_rate=sr,return_tensors='pt').input_features
    with torch.no_grad():
        hidden=model.model.encoder(inputs,output_hidden_states=True,return_dict=True).hidden_states
        features=torch.stack(hidden,dim=2)[0] # 1500, 5, 384
        windows=[]
        for frame in range(64):
            indices=torch.arange(frame*2-4,frame*2+6).clamp(0,int(len(samples)/320)-1)
            windows.append(features[indices].reshape(50,384))
        recognition=recognizer({'raw':samples,'sampling_rate':sr},return_timestamps='word',generate_kwargs={'language':'english','task':'transcribe','max_new_tokens':128})
    aligned=np.zeros(64,dtype=np.int64);unknown=[]
    for chunk in recognition.get('chunks',[]):
        word=re.sub(r"[^a-z']",'',chunk['text'].lower())
        if not word:continue
        pron=lexicon.get(word)
        if pron is None:pron=['UNK'];unknown.append(word)
        start,end=chunk['timestamp'];start=0 if start is None else start;end=64/25 if end is None else end
        for index,p in enumerate(pron):
            a=max(0,min(63,int((start+(end-start)*index/len(pron))*25)))
            b=max(a+1,min(64,int((start+(end-start)*(index+1)/len(pron))*25)))
            aligned[a:b]=idmap.get(p,40)
    if not (aligned>0).any():raise RuntimeError('No real speech aligned for '+row['id'])
    windows_ph=np.stack([aligned[np.arange(t-5,t+6).clip(0,63)] for t in range(64)])
    record=dict(id=row['id'],transcript=recognition['text'],unknown_words=unknown,non_silence_frames=int((aligned>0).sum()))
    torch.save(dict(whisper=torch.stack(windows).to(torch.bfloat16),phoneme_win=torch.from_numpy(windows_ph),record=record),target)
    records.append(record);print(json.dumps(dict(stage='Whisper_and_phonemes',completed=i+1,total=50,**record)),flush=True)
(H/'outputs/cpu-conditions.json').write_text(json.dumps(dict(records=records,phoneme_table=idmap,phoneme_source='Whisper word timestamps + CMU pronunciation dictionary; not the unpublished WhisperX supplementary mapping',style_source='original Deep3DFaceRecon resnet50 epoch_20, expression coefficients 80:144'),indent=2)+'\n')
