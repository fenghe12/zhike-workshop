from pathlib import Path
import argparse,importlib,sys,json,shutil
import numpy as np,torch
from PIL import Image,ImageDraw
p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--data',required=True);p.add_argument('--config',required=True);p.add_argument('--output',required=True);a=p.parse_args()
repo=Path(a.repo);data=Path(a.data);output=Path(a.output);output.mkdir(exist_ok=True)
torch.npu.set_device(0);torch.set_default_device('npu:0');sys.path.insert(0,str(repo/'NeRFs/HeadNeRF'))
native=importlib.import_module('run_nerf');args=native.config_parser().parse_args(['--config',a.config])
_,test_kwargs,step,*_=native.create_nerf(args)
checkpoint=sorted((Path(args.basedir)/args.expname).glob('*_head.tar'))[-1]
state=torch.load(checkpoint,map_location='cpu',weights_only=False)
completed=int(state.get('completed_iterations',state['global_step']+1))
net=native.AudioNet(args.dim_aud,args.win_size).to('npu:0');net.load_state_dict(state['network_audnet_state_dict']);net.eval()
meta=json.loads((data/'transforms_val.json').read_text());selected=[meta['frames'][i] for i in [0,len(meta['frames'])//2,len(meta['frames'])-1]]
audio=np.load(data/'aud.npy');features=torch.as_tensor(np.stack([audio[min(x['aud_id'],len(audio)-1)] for x in selected]),device='npu:0',dtype=torch.float32)
poses=torch.tensor([x['transform_matrix'] for x in selected],device='npu:0');background=torch.tensor(np.asarray(Image.open(data/'bc.jpg').convert('RGB')).copy(),device='npu:0',dtype=torch.float32)/255
hw=[450,450,meta['focal_len'],meta['cx'],meta['cy']];test_kwargs.update(near=args.near,far=args.far)
with torch.inference_mode():native.render_path(poses,net(features),background,hw,args.chunk,test_kwargs,savedir=str(output))
sheet=Image.new('RGB',(900,3*480),'white');draw=ImageDraw.Draw(sheet);metrics=[]
for row,frame in enumerate(selected):
 reference=data/'head_imgs'/f'{frame["img_id"]}.jpg';shutil.copy2(reference,output/f'reference-{row}.jpg')
 sheet.paste(Image.open(reference),(0,row*480+30));sheet.paste(Image.open(output/f'{row:03d}.png'),(450,row*480+30))
 predicted=np.asarray(Image.open(output/f'{row:03d}.png').convert('RGB'),dtype=np.float32)/255
 actual=np.asarray(Image.open(reference).convert('RGB'),dtype=np.float32)/255
 mse=float(np.mean((predicted-actual)**2));metrics.append({'image_id':frame['img_id'],'mse':mse,'psnr_db':float(-10*np.log10(max(mse,1e-12)))})
 draw.text((10,row*480+10),f'Validation reference {frame["img_id"]}',fill='black');draw.text((460,row*480+10),f'Head model after {completed} updates',fill='black')
sheet.save(output/'training-preview.jpg')
(output/'preview.json').write_text(json.dumps({'head_optimizer_updates':completed,'validation_frames':metrics,'image_ids':[x['img_id'] for x in selected],'size':[450,450],'N_samples':64,'N_importance':128,'scope':'Three held-out camera poses; early head-only training preview, not a converged quality assessment.'},indent=2)+'\n')
print('Native-resolution early training preview saved',flush=True)
