from pathlib import Path
import argparse,ast,json,os,sys,time
import cv2
import numpy as np
import torch
from PIL import Image
from torchvision import transforms
from sklearn.neighbors import NearestNeighbors
parser=argparse.ArgumentParser();parser.add_argument('--repo',required=True);parser.add_argument('--data',required=True)
args=parser.parse_args();repo=Path(args.repo);data=Path(args.data)
sys.path.insert(0,str(repo/'data_util/face_parsing'))
import resnet
# The complete parsing checkpoint supplies every backbone parameter.
resnet.Resnet18.init_weight=lambda self:None
from model import BiSeNet
from test import vis_parsing_maps
net=BiSeNet(n_classes=19)
checkpoint=repo/'data_util/face_parsing/79999_iter.pth'
net.load_state_dict(torch.load(checkpoint,map_location='cpu',weights_only=True),strict=True)
net=net.to('npu:0').eval()
normalize=transforms.Compose([transforms.ToTensor(),transforms.Normalize((0.485,0.456,0.406),(0.229,0.224,0.225))])
files=sorted((data/'ori_imgs').glob('*.jpg'),key=lambda p:int(p.stem))
(data/'parsing').mkdir(exist_ok=True)
started=time.time()
with torch.inference_mode():
    for index,path in enumerate(files):
        original=Image.open(path);size=original.size
        image=original.resize((512,512),Image.BILINEAR).convert('RGB')
        prediction=net(normalize(image).unsqueeze(0).to('npu:0'))[0]
        classes=prediction.squeeze(0).cpu().numpy().argmax(0)
        vis_parsing_maps(image,classes,stride=1,save_im=True,save_path=str(data/'parsing'/(path.stem+'.png')),img_size=size)
        if (index+1)%50==0:print(json.dumps({'parsed_background_frames':index+1,'total':len(files)}),flush=True)
del net;torch.npu.empty_cache()
ids=[]
for name in ['transforms_train.json','transforms_val.json']:
    ids.extend(x['img_id'] for x in json.loads((data/name).read_text())['frames'])
ids=sorted(set(ids));assert [int(p.stem) for p in files]==ids[::20]
image=cv2.imread(str(files[0]));height,width=image.shape[:2]
tree=ast.parse((repo/'data_util/process_data.py').read_text())
block=next(node for node in tree.body if isinstance(node,ast.If) and ast.unparse(node.test)=='running_step == 4')
namespace={'np':np,'cv2':cv2,'os':os,'NearestNeighbors':NearestNeighbors,
           'id_dir':str(data),'ori_imgs_dir':str(data/'ori_imgs'),'valid_img_ids':ids,'valid_img_num':len(ids),'h':height,'w':width}
exec(compile(ast.fix_missing_locations(ast.Module(body=block.body,type_ignores=[])),'official_background_step','exec'),namespace)
assert cv2.imread(str(data/'bc.jpg')).shape[:2]==(450,450)
report={'completed':True,'native_size':[450,450],'background_frames':len(files),
        'method':'Official face parser and unchanged step-4 background routine; provided pretrained valid poses used.',
        'elapsed_seconds':round(time.time()-started,2)}
(data/'background.metadata.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report),flush=True)
