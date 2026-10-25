"""CPU-only paired frame metrics for the newly trained checkpoints."""
import os,json,io,subprocess
from pathlib import Path
import torch,numpy as np,cv2,requests
from torchmetrics.functional.image.lpips import _LPIPS
H=Path(os.environ['ZERO100_SESSION']);DATA=H.parent/'ditalker-cogportrait-50hdtf-200steps-20261025'
torch.set_num_threads(8)
metric=_LPIPS(net='alex',pnet_rand=True,pretrained=True).cpu().eval().requires_grad_(False)
plan=json.loads((H/'checkpoint-plans/metric.private.json').read_text());buffer=io.BytesIO()
with requests.get(plan['read_url'],stream=True,timeout=(30,180)) as response:
    if response.status_code!=200:raise RuntimeError('Private metric weights unavailable')
    for block in response.iter_content(8*1024**2):buffer.write(block)
assert buffer.tell()==plan['bytes'];buffer.seek(0);weights=torch.load(buffer,map_location='cpu',weights_only=True);buffer.close()
mapped={n:weights['features.'+n.split('.',1)[1]] for n in metric.net.state_dict()};assert len(mapped)==10;metric.net.load_state_dict(mapped,strict=True)
def ssim(a,b):
    a=a.astype(float);b=b.astype(float);f=lambda x:cv2.GaussianBlur(x,(11,11),1.5)[5:-5,5:-5]
    ma,mb=f(a),f(b);va=f(a*a)-ma*ma;vb=f(b*b)-mb*mb;cov=f(a*b)-ma*mb
    return float((((2*ma*mb+6.5025)*(2*cov+58.5225))/((ma*ma+mb*mb+6.5025)*(va+vb+58.5225))).mean())
references={};report=dict(protocol='RGB512, source frames0,4,...60; PSNR/SSIM and LPIPSv0.1 AlexNet, paired per-frame training-set diagnostic',variants={})
for variant in ['ditalker-case1-cfg1','ditalker-case1-cfg7','ditalker-case2-cfg1']:
    folder=H/'outputs/previews'/variant;info=json.loads((folder/'result.json').read_text());identifier=info['source_sample']
    if identifier not in references:
        raw=subprocess.run([str(H.parents[1]/'toolchains/ffmpeg/bin/ffmpeg'),'-v','error','-i',str(DATA/'inputs/clips'/(identifier+'.mp4')),'-vf','crop=min(iw\\,ih):min(iw\\,ih),scale=512:512','-frames:v','64','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True).stdout
        references[identifier]=np.frombuffer(raw,np.uint8).reshape(64,512,512,3)[::4].copy()
    target=references[identifier];a=np.load(folder/'generated.frames.npy');assert a.shape==target.shape
    values=[]
    with torch.no_grad():
        for i in range(0,16,4):
            x=torch.from_numpy(a[i:i+4].copy()).permute(0,3,1,2).float()/127.5-1;y=torch.from_numpy(target[i:i+4].copy()).permute(0,3,1,2).float()/127.5-1
            values.extend(metric(x,y).flatten().tolist())
    mse=np.square(a.astype(float)-target).mean(axis=(1,2,3));scores=dict(sample=identifier,split='training',frames=16,cfg=info['cfg'],psnr_db=float(np.mean(10*np.log10(255**2/mse))),ssim_rgb=float(np.mean([ssim(x,y) for x,y in zip(a,target)])),lpips=float(np.mean(values)))
    report['variants'][variant]=scores;print(json.dumps(dict(variant=variant,**scores)),flush=True)
    (H/'outputs/preview-metrics.json').write_text(json.dumps(report,indent=2)+'\n')
report['completed']=True;(H/'outputs/preview-metrics.json').write_text(json.dumps(report,indent=2)+'\n')
