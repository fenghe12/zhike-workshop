from pathlib import Path
from datetime import datetime
import argparse,ast,json,os,shutil,sys,time
import cv2,numpy as np,torch
from PIL import Image
from torchvision import transforms
parser=argparse.ArgumentParser();parser.add_argument('--repo',required=True);parser.add_argument('--original',required=True);parser.add_argument('--data',required=True);args=parser.parse_args()
repo=Path(args.repo);original=Path(args.original);data=Path(args.data);data.mkdir(parents=True,exist_ok=True)
started=time.time()
for name in ['ori_imgs','parsing','head_imgs','com_imgs']:(data/name).mkdir(exist_ok=True)
for name in ['aud.npy','aud.wav','transforms_train.json','transforms_val.json','bc.jpg']:
 target=data/name
 if not target.exists():target.symlink_to(original/name)
ids=[]
for split in ['train','val']:ids.extend(x['img_id'] for x in json.loads((data/f'transforms_{split}.json').read_text())['frames'])
ids=sorted(set(ids));assert len(ids)==8000
video=repo/'dataset/vids/Obama.mp4';capture=cv2.VideoCapture(str(video));index=0;wanted=set(ids)
while True:
 ok,frame=capture.read()
 if not ok:break
 if index in wanted:
  p=data/'ori_imgs'/f'{index}.jpg'
  if not p.exists():assert cv2.imwrite(str(p),frame)
 index+=1
capture.release();assert index==8000
for p in (original/'parsing').glob('*.png'):
 target=data/'parsing'/p.name
 if not target.exists():shutil.copy2(p,target)
sys.path.insert(0,str(repo/'data_util/face_parsing'))
import resnet
resnet.Resnet18.init_weight=lambda self:None
from model import BiSeNet
from test import vis_parsing_maps
net=BiSeNet(n_classes=19)
net.load_state_dict(torch.load(repo/'data_util/face_parsing/79999_iter.pth',map_location='cpu',weights_only=True),strict=True)
net=net.to('npu:0').eval()
normalize=transforms.Compose([transforms.ToTensor(),transforms.Normalize((0.485,0.456,0.406),(0.229,0.224,0.225))])
with torch.inference_mode():
 for count,index in enumerate(ids,1):
  output=data/'parsing'/f'{index}.png'
  if not output.exists():
   original_image=Image.open(data/'ori_imgs'/f'{index}.jpg');size=original_image.size
   image=original_image.resize((512,512),Image.BILINEAR).convert('RGB')
   logits=net(normalize(image).unsqueeze(0).to('npu:0'))[0]
   classes=logits.squeeze(0).cpu().numpy().argmax(0)
   vis_parsing_maps(image,classes,stride=1,save_im=True,save_path=str(output),img_size=size)
  if count%250==0:print(json.dumps({'parsed_frames':count,'total_frames':len(ids),'elapsed_seconds':round(time.time()-started,2)}),flush=True)
del net;torch.npu.empty_cache()
tree=ast.parse((repo/'data_util/process_data.py').read_text())
block=next(node for node in tree.body if isinstance(node,ast.If) and ast.unparse(node.test)=='running_step == 5')
namespace={'np':np,'cv2':cv2,'os':os,'id_dir':str(data),'ori_imgs_dir':str(data/'ori_imgs'),'parsing_dir':str(data/'parsing'),'head_imgs_dir':str(data/'head_imgs'),'com_imgs_dir':str(data/'com_imgs'),'valid_img_ids':ids}
exec(compile(ast.fix_missing_locations(ast.Module(body=block.body,type_ignores=[])),'official_training_image_step','exec'),namespace)
for folder in ['ori_imgs','parsing','head_imgs','com_imgs']:
 suffix='*.png' if folder=='parsing' else '*.jpg'
 assert len(list((data/folder).glob(suffix)))==8000,folder
features=np.load(data/'aud.npy');assert features.shape==(7999,16,29) and np.isfinite(features).all()
record={'completed_at':datetime.now().astimezone().isoformat(),'video_frames':8000,'training_frames':7272,'validation_frames':728,'native_size':[450,450],
'face_parser':'Official complete BiSeNet checkpoint','image_generation':'Unchanged official process_data.py step 5','poses_and_audio':'Official pretrained camera poses and verified full DeepSpeech features reused','elapsed_seconds':round(time.time()-started,2)}
(data/'training-data.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record),flush=True)
