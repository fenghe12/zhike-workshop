"""LPIPS v0.1 AlexNet, CPU, with pretrained feature weights streamed from private OBS."""
import os,sys,json,io,subprocess,time
from pathlib import Path
H=Path(os.environ['AUDIT_SESSION']);DATA=H.parent/'ditalker-cogportrait-50hdtf-200steps-20261025';ZERO=H.parent/'ditalker-cogportrait-50hdtf-100steps-allzero-20261025'
import torch,numpy as np,requests
from torchmetrics.functional.image.lpips import _LPIPS
torch.set_num_threads(8)
metric=_LPIPS(net='alex',pnet_rand=True,pretrained=True).cpu().eval().requires_grad_(False)
plan=json.loads((H/'checkpoint-plans/metric.private.json').read_text())
buffer=io.BytesIO()
with requests.get(plan['read_url'],stream=True,timeout=(30,180)) as response:
    assert response.status_code==200
    for block in response.iter_content(8*1024**2):buffer.write(block)
assert buffer.tell()==plan['bytes'];buffer.seek(0);weights=torch.load(buffer,map_location='cpu',weights_only=True);buffer.close()
mapped={n:weights['features.'+n.split('.',1)[1]] for n in metric.net.state_dict()}
metric.net.load_state_dict(mapped,strict=True)
assert len(mapped)==10
ID='WDA_KirstenGillibrand_000_8181_8261'
raw=subprocess.run([str(H.parents[1]/'toolchains/ffmpeg/bin/ffmpeg'),'-v','error','-i',str(DATA/'inputs/clips'/(ID+'.mp4')),'-vf','crop=min(iw\\,ih):min(iw\\,ih),scale=512:512','-frames:v','64','-pix_fmt','rgb24','-f','rawvideo','-'],capture_output=True,check=True).stdout
reference=np.frombuffer(raw,np.uint8).reshape(64,512,512,3)
paths={
 'ditalker100_cfg1':ZERO/'outputs/previews/ditalker/generated.frames.npy',
 'ditalker100_cfg7':ZERO/'outputs/previews/ditalker-cfg7/generated.frames.npy',
 'cogportrait_pose100':ZERO/'outputs/previews/cogportrait/generated.frames.npy',
 'ditalker220_cfg1_control':H.parent/'ditalker-cogportrait-preview220-1h-20261025/outputs/ditalker-cfg1/generated.frames.npy',
 'ditalker100_native_mask':H/'outputs/di/strict100-native-mask.frames.npy',
 'ditalker_initialzero_native_mask':H/'outputs/di/initialzero-native-mask.frames.npy',
}
report=dict(protocol=dict(metric='LPIPS v0.1, AlexNet, pretrained calibrated linear heads and all ImageNet feature weights',implementation='torchmetrics.functional.image.lpips._LPIPS',device='cpu',spatial_resolution=[512,512],input_range=[-1,1],pretrained_feature_tensors_loaded=10,training_split=True,identities=1),variants={})
for name,path in paths.items():
    a=np.load(path,allow_pickle=False);target=reference[::4] if name.startswith('ditalker') else reference;assert a.shape==target.shape
    values=[]
    with torch.no_grad():
        for i in range(0,len(a),4):
            x=torch.from_numpy(a[i:i+4].copy()).permute(0,3,1,2).float()/127.5-1
            y=torch.from_numpy(target[i:i+4].copy()).permute(0,3,1,2).float()/127.5-1
            values.extend(metric(x,y).flatten().tolist())
    report['variants'][name]=dict(mean=float(np.mean(values)),per_frame=values,frames=len(values));(H/'outputs/lpips.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(variant=name,lpips=report['variants'][name]['mean'],frames=len(values))),flush=True)
report['completed']=True;(H/'outputs/lpips.json').write_text(json.dumps(report,indent=2)+'\n')
